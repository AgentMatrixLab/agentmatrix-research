"""TEST-ONLY tests for merging parallel shard batch manifests."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from research_core.factor_lab.merge_batches import MergeError, merge_batch_manifests

REPO_ROOT = Path(__file__).resolve().parents[1]
IDENTITY = {
    "code_commit": "a" * 40,
    "segment": "oos",
    "panel_file_sha256": "p" * 64,
    "factor_file_sha256": "f" * 64,
    "configuration_sha256": "c" * 64,
    "data_snapshot_hash": "d" * 64,
    "factor_sidecar_data_start": "2020-01-02",
    "factor_sidecar_data_end": "2026-08-31",
    "panel_price_basis": "post_adjusted",
}


def _write_shard(
    tmp_path: Path,
    name: str,
    factors: list[tuple[str, str, bool]],
    *,
    identity_overrides: dict[str, str] | None = None,
) -> Path:
    shard_dir = tmp_path / name
    shard_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for factor_id, status, risk in factors:
        results.append(
            {
                "factor_id": factor_id,
                "status": status,
                "risk_exposure": risk,
                "window": 22,
                "failed_gates": [] if status == "validated" else ["rank_ic"],
                "reason": "" if status == "validated" else "failed_gate=rank_ic",
                "result_hash": hashlib.sha256(factor_id.encode()).hexdigest(),
                "artifacts": {},
            }
        )
    summary = shard_dir / "batch_summary.csv"
    with summary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "factor_id",
                "status",
                "risk_exposure",
                "window",
                "failed_gates",
                "reason",
                "result_hash",
            ],
        )
        writer.writeheader()
        for entry in results:
            writer.writerow(
                {
                    "factor_id": entry["factor_id"],
                    "status": entry["status"],
                    "risk_exposure": "true" if entry["risk_exposure"] else "false",
                    "window": "22",
                    "failed_gates": ";".join(entry["failed_gates"]),
                    "reason": entry["reason"],
                    "result_hash": entry["result_hash"],
                }
            )
    manifest = {
        "batch_id": name,
        "candidate_count": len(factors),
        "results": results,
        "outputs": {
            "batch_summary_csv": str(summary),
            "batch_summary_sha256": hashlib.sha256(summary.read_bytes()).hexdigest(),
        },
        **IDENTITY,
    }
    manifest.update(identity_overrides or {})
    path = shard_dir / "batch_manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


def test_only_merges_shards_that_each_have_their_own_factor_file(tmp_path: Path) -> None:
    """A real sharded run gives every shard its own factor file, so the digests differ.

    Requiring `factor_file_sha256` equality made every sharded run unmergeable: the field is
    split-dependent by construction. The digests must still be recorded per shard.
    """
    shard_a = _write_shard(
        tmp_path,
        "shard_a",
        [("reversal_1m", "validated", False)],
        identity_overrides={"factor_file_sha256": "a" * 64, "factor_file": "shard_a.parquet"},
    )
    shard_b = _write_shard(
        tmp_path,
        "shard_b",
        [("rsi_6", "validated", False)],
        identity_overrides={"factor_file_sha256": "b" * 64, "factor_file": "shard_b.parquet"},
    )

    payload = merge_batch_manifests([shard_a, shard_b], output_dir=tmp_path / "merged_split")

    assert payload["shard_count"] == 2
    assert payload["counts"]["validated"] == 2
    # No single factor file exists for a merged batch, so the top-level digest must not claim one.
    assert payload["factor_file_sha256"] is None
    assert payload["factor_file"] is None
    recorded = {
        entry["batch_id"]: entry["factor_file_sha256"] for entry in payload["shards"]
    }
    assert recorded == {"shard_a": "a" * 64, "shard_b": "b" * 64}
    assert payload["factor_files_by_shard"]["shard_b"]["factor_file"] == "shard_b.parquet"
    # Dropping the per-file digest must not drop the coverage contract that makes shards comparable.
    assert payload["identity"]["factor_sidecar_data_start"] == IDENTITY["factor_sidecar_data_start"]


def test_only_refuses_shards_with_different_factor_coverage(tmp_path: Path) -> None:
    """The compensating check: different declared factor coverage is still refused."""
    shard_a = _write_shard(tmp_path, "shard_a", [("reversal_1m", "validated", False)])
    shard_b = _write_shard(
        tmp_path,
        "shard_b",
        [("rsi_6", "validated", False)],
        identity_overrides={"factor_sidecar_data_end": "2025-01-01"},
    )

    with pytest.raises(MergeError, match="factor_sidecar_data_end"):
        merge_batch_manifests([shard_a, shard_b], output_dir=tmp_path / "merged_bad_coverage")


def test_only_merges_disjoint_shards_and_recomputes_counts(tmp_path: Path) -> None:
    shard_a = _write_shard(
        tmp_path,
        "shard_a",
        [("reversal_1m", "validated", False), ("momentum_20", "rejected", False)],
    )
    shard_b = _write_shard(
        tmp_path,
        "shard_b",
        [("rsi_6", "validated", True), ("alpha002", "validated", False)],
    )

    payload = merge_batch_manifests([shard_a, shard_b], output_dir=tmp_path / "merged")

    assert payload["shard_count"] == 2
    assert payload["candidate_count"] == 4
    assert payload["counts"]["validated"] == 3
    assert payload["counts"]["rejected"] == 1
    assert payload["validated_effective_alpha"] == ["reversal_1m", "alpha002"]
    assert payload["validated_risk_exposure"] == ["rsi_6"]
    assert [entry["factor_id"] for entry in payload["results"]] == [
        "reversal_1m",
        "momentum_20",
        "rsi_6",
        "alpha002",
    ]
    assert payload["identity"]["panel_file_sha256"] == IDENTITY["panel_file_sha256"]
    assert [shard["batch_id"] for shard in payload["shards"]] == ["shard_a", "shard_b"]
    assert Path(payload["batch_manifest_path"]).is_file()
    # the merged manifest must still carry the run identity, or the cross-check cannot verify it
    assert payload["code_commit"] == IDENTITY["code_commit"]
    assert payload["segment"] == IDENTITY["segment"]
    assert payload["panel_file_sha256"] == IDENTITY["panel_file_sha256"]
    assert payload["panel_price_basis"] == IDENTITY["panel_price_basis"]

    merged_summary = Path(payload["outputs"]["batch_summary_csv"])
    with merged_summary.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert [row["factor_id"] for row in rows] == ["reversal_1m", "momentum_20", "rsi_6", "alpha002"]
    assert payload["outputs"]["batch_summary_sha256"] == hashlib.sha256(merged_summary.read_bytes()).hexdigest()


def test_only_refuses_to_merge_shards_that_ran_on_different_inputs(tmp_path: Path) -> None:
    shard_a = _write_shard(tmp_path, "shard_a", [("reversal_1m", "validated", False)])
    shard_b = _write_shard(
        tmp_path,
        "shard_b",
        [("rsi_6", "validated", False)],
        identity_overrides={"panel_file_sha256": "q" * 64},
    )

    with pytest.raises(MergeError, match="panel_file_sha256"):
        merge_batch_manifests([shard_a, shard_b], output_dir=tmp_path / "merged_bad")


def test_only_refuses_to_merge_shards_that_ran_on_different_commits(tmp_path: Path) -> None:
    shard_a = _write_shard(tmp_path, "shard_a", [("reversal_1m", "validated", False)])
    shard_b = _write_shard(
        tmp_path,
        "shard_b",
        [("rsi_6", "validated", False)],
        identity_overrides={"code_commit": "b" * 40},
    )

    with pytest.raises(MergeError, match="code_commit"):
        merge_batch_manifests([shard_a, shard_b], output_dir=tmp_path / "merged_bad_commit")


def test_only_refuses_overlapping_shards(tmp_path: Path) -> None:
    shard_a = _write_shard(tmp_path, "shard_a", [("reversal_1m", "validated", False)])
    shard_b = _write_shard(tmp_path, "shard_b", [("reversal_1m", "rejected", False)])

    with pytest.raises(MergeError, match="disjoint"):
        merge_batch_manifests([shard_a, shard_b], output_dir=tmp_path / "merged_overlap")


def test_only_merge_script_exit_codes(tmp_path: Path) -> None:
    shard_a = _write_shard(tmp_path, "shard_a", [("reversal_1m", "validated", False)])
    shard_b = _write_shard(tmp_path, "shard_b", [("rsi_6", "rejected", False)])
    ok = subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8",
            str(REPO_ROOT / "scripts" / "merge_batch_manifests.py"),
            "--shards",
            str(shard_a),
            str(shard_b),
            "--output-dir",
            str(tmp_path / "merged_cli"),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert ok.returncode == 0, ok.stdout + ok.stderr
    printed = json.loads(ok.stdout)
    assert printed["shard_count"] == 2
    assert printed["counts"]["validated"] == 1

    bad = subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8",
            str(REPO_ROOT / "scripts" / "merge_batch_manifests.py"),
            "--shards",
            str(shard_a),
            str(shard_a),
            "--output-dir",
            str(tmp_path / "merged_cli_bad"),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert bad.returncode == 2, bad.stdout + bad.stderr
    assert "disjoint" in json.loads(bad.stdout)["reason"]
