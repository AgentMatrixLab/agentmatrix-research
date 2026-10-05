from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

# Fields that must be byte-identical across shards, otherwise the shards are not comparable and
# merging them would fabricate a single run that never happened.
#
# `factor_file_sha256` is deliberately NOT here. A shard is handed its own slice of the candidate
# list and therefore writes its OWN factor file, so that digest is **split-dependent by
# construction**: N honest shards produce N different digests, and requiring equality made every
# real sharded run unmergeable. The digests are still recorded, per shard, in
# `factor_files_by_shard` -- provenance is preserved, it just is not an equality constraint.
#
# What actually has to agree for the verdicts to be comparable is the *coverage contract* of those
# files: the same panel, the same gate configuration, the same snapshot, the same declared data
# range and the same price basis. All of those remain in the list below, so dropping the raw
# per-file digest removes an impossible constraint without removing a real one.
IDENTITY_FIELDS = (
    "code_commit",
    "segment",
    "panel_file_sha256",
    "configuration_sha256",
    "data_snapshot_hash",
    "factor_sidecar_data_start",
    "factor_sidecar_data_end",
    "panel_price_basis",
)

# Split-dependent: recorded per shard, never compared for equality across shards.
PER_SHARD_FIELDS = (
    "factor_file",
    "factor_file_sha256",
)


class MergeError(ValueError):
    """Raised when shard manifests cannot be merged honestly."""


@dataclass(frozen=True)
class Shard:
    path: Path
    sha256: str
    payload: dict[str, Any]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_shard(path: str | Path) -> Shard:
    manifest_path = Path(path)
    if not manifest_path.is_file():
        raise MergeError(f"shard manifest does not exist: {manifest_path}")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise MergeError(f"shard manifest has no results list: {manifest_path}")
    return Shard(path=manifest_path, sha256=_sha256_file(manifest_path), payload=payload)


def _check_identity(shards: list[Shard]) -> dict[str, Any]:
    reference = shards[0]
    for field in IDENTITY_FIELDS:
        expected = reference.payload.get(field)
        for shard in shards[1:]:
            actual = shard.payload.get(field)
            if actual != expected:
                raise MergeError(
                    f"shard {shard.path.name} disagrees on {field}: "
                    f"{actual!r} != {expected!r} (reference {reference.path.name}); "
                    "refusing to merge shards that did not run on the same inputs"
                )
    return {field: reference.payload.get(field) for field in IDENTITY_FIELDS}


def _counts(entries: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"validated": 0, "rejected": 0, "train_only": 0, "needs_human": 0, "error": 0}
    for entry in entries:
        status = str(entry.get("status"))
        counts[status] = counts.get(status, 0) + 1
    counts["validated_effective_alpha"] = sum(
        1 for entry in entries if entry.get("status") == "validated" and not entry.get("risk_exposure")
    )
    counts["validated_risk_exposure"] = sum(
        1 for entry in entries if entry.get("status") == "validated" and entry.get("risk_exposure")
    )
    return counts


def merge_batch_manifests(
    shard_manifests: Iterable[str | Path],
    *,
    output_dir: str | Path,
    candidates_path: str | Path | None = None,
) -> dict[str, Any]:
    """Merge independently produced shard manifests into one, without touching any verdict."""
    paths = [Path(path) for path in shard_manifests]
    if not paths:
        raise MergeError("at least one shard manifest is required")
    shards = [_load_shard(path) for path in paths]
    identity = _check_identity(shards)

    entries: list[dict[str, Any]] = []
    seen: dict[str, str] = {}
    for shard in shards:
        for entry in shard.payload["results"]:
            factor_id = str(entry.get("factor_id"))
            if not factor_id:
                raise MergeError(f"shard {shard.path.name} has a result without a factor_id")
            if factor_id in seen:
                raise MergeError(
                    f"factor {factor_id!r} appears in both {seen[factor_id]} and {shard.path.name}; "
                    "shards must be disjoint"
                )
            seen[factor_id] = shard.path.name
            entries.append(entry)

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    summary_rows: list[dict[str, str]] = []
    summary_fields: list[str] = []
    for shard in shards:
        summary_path = (shard.payload.get("outputs") or {}).get("batch_summary_csv")
        if not summary_path or not Path(summary_path).is_file():
            continue
        with Path(summary_path).open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            for field in reader.fieldnames or []:
                if field not in summary_fields:
                    summary_fields.append(field)
            summary_rows.extend(reader)
    merged_summary_path: Path | None = None
    if summary_rows:
        merged_summary_path = output_root / "batch_summary.csv"
        with merged_summary_path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=summary_fields)
            writer.writeheader()
            writer.writerows(summary_rows)

    counts = _counts(entries)
    payload: dict[str, Any] = {
        "batch_id": output_root.name,
        "created_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "merged": True,
        "merge_rule": (
            "concatenate shard results after verifying every shard shares the same code commit, "
            "split-independent identity hashes and segment; no verdict is recomputed or altered"
        ),
        "shards": [
            {
                "path": str(shard.path),
                "sha256": shard.sha256,
                "batch_id": shard.payload.get("batch_id"),
                "candidate_count": shard.payload.get("candidate_count"),
                "counts": shard.payload.get("counts"),
                # Split-dependent, so recorded per shard rather than asserted equal.
                "factor_file": shard.payload.get("factor_file"),
                "factor_file_sha256": shard.payload.get("factor_file_sha256"),
            }
            for shard in shards
        ],
        # Explicit, because the top-level `factor_file_sha256` below is None: a merged batch does
        # not have one factor file, it has one per shard, and pretending otherwise would let the
        # cross-check verify a digest that no shard ever produced.
        "factor_files_by_shard": {
            str(shard.payload.get("batch_id") or shard.path.parent.name): {
                "factor_file": shard.payload.get("factor_file"),
                "factor_file_sha256": shard.payload.get("factor_file_sha256"),
            }
            for shard in shards
        },
        "shard_count": len(shards),
        "identity": identity,
        "candidate_count": len(entries),
        "factor_ids": [str(entry.get("factor_id")) for entry in entries],
        "counts": counts,
        "validated": [str(e.get("factor_id")) for e in entries if e.get("status") == "validated"],
        "validated_effective_alpha": [
            str(e.get("factor_id"))
            for e in entries
            if e.get("status") == "validated" and not e.get("risk_exposure")
        ],
        "validated_risk_exposure": [
            str(e.get("factor_id"))
            for e in entries
            if e.get("status") == "validated" and e.get("risk_exposure")
        ],
        "rejected": [str(e.get("factor_id")) for e in entries if e.get("status") == "rejected"],
        "errors": [str(e.get("factor_id")) for e in entries if e.get("status") == "error"],
        "needs_human": [str(e.get("factor_id")) for e in entries if e.get("status") == "needs_human"],
        "results": entries,
        "outputs": {
            "batch_summary_csv": str(merged_summary_path) if merged_summary_path else None,
            "batch_summary_sha256": (
                _sha256_file(merged_summary_path) if merged_summary_path is not None else None
            ),
        },
    }
    for field in (
        "panel_file",
        "panel_file_sha256",
        "panel_price_basis",
        "data_snapshot_hash",
        "factor_sidecar_data_start",
        "factor_sidecar_data_end",
        "configuration_file",
        "configuration_sha256",
        "parameters",
    ):
        if shards[0].payload.get(field) is not None:
            payload[field] = shards[0].payload[field]
    # Left explicitly unset: see `factor_files_by_shard`. `cross_check` skips a digest that is
    # declared as None, which is the honest outcome here -- there is no single file to hash.
    payload["factor_file"] = None
    payload["factor_file_sha256"] = None
    # The merged manifest must still carry the run identity, otherwise the cross-check (and any
    # human reading it) cannot tell which code and which split produced these verdicts.
    payload["code_commit"] = identity["code_commit"]
    payload["segment"] = identity["segment"]
    if candidates_path is not None:
        payload["candidates_file"] = Path(candidates_path).name
        payload["candidates_file_sha256"] = _sha256_file(Path(candidates_path))

    manifest_path = output_root / "batch_manifest.json"
    manifest_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {**payload, "batch_manifest_path": str(manifest_path)}
