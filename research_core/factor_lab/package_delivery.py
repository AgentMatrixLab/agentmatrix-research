from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from research_core.factor_lab.factor_catalog import (
    build_factor_catalog,
    index_from_batch_manifest,
    index_from_results_root,
    write_factor_catalog,
)


class DeliveryPackagingError(ValueError):
    """Raised when a delivery package cannot be assembled."""


VALIDATED = "validated"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_files(entry: dict[str, Any]) -> dict[str, str]:
    artifacts = entry.get("artifacts") or {}
    return {
        name: str(path)
        for name, path in artifacts.items()
        if name in {"report", "result", "manifest"} and path and Path(path).is_file()
    }


def build_delivery_package(
    *,
    output_dir: str | Path,
    batch_manifest: str | Path | None = None,
    results_root: str | Path | None = None,
    candidates_path: str | Path | None = None,
    copy_artifacts: bool = True,
) -> dict[str, Any]:
    """Assemble a delivery package that contains **only** validated factors.

    Rejected, errored, needs-human and never-run factors are listed with their status and
    reason so the exclusions are auditable, but none of their artifacts are copied in.
    """
    if batch_manifest is not None and results_root is not None:
        raise DeliveryPackagingError("pass either batch_manifest or results_root, not both")
    if batch_manifest is None and results_root is None:
        raise DeliveryPackagingError("pass either batch_manifest or results_root")

    if batch_manifest is not None:
        index = index_from_batch_manifest(batch_manifest)
        source_path = Path(batch_manifest)
    else:
        index = index_from_results_root(results_root)  # type: ignore[arg-type]
        source_path = Path(results_root)  # type: ignore[arg-type]

    package_root = Path(output_dir)
    package_root.mkdir(parents=True, exist_ok=True)
    factors_root = package_root / "factors"

    included: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for factor_id in sorted(index):
        entry = index[factor_id]
        if entry["status"] != VALIDATED:
            excluded.append(
                {
                    "factor_id": factor_id,
                    "status": entry["status"],
                    "failed_gates": entry["failed_gates"],
                    "reason": entry["reason"],
                }
            )
            continue

        files = _artifact_files(entry)
        record: dict[str, Any] = {
            "factor_id": factor_id,
            "status": entry["status"],
            "result_hash": entry.get("result_hash"),
            "artifacts": {},
        }
        if copy_artifacts:
            target_dir = factors_root / factor_id
            target_dir.mkdir(parents=True, exist_ok=True)
            for name, source in files.items():
                target = target_dir / Path(source).name
                shutil.copy2(source, target)
                record["artifacts"][name] = {
                    "path": str(target.relative_to(package_root)).replace("\\", "/"),
                    "sha256": _sha256_file(target),
                    "source": source,
                }
        else:
            for name, source in files.items():
                record["artifacts"][name] = {
                    "path": source,
                    "sha256": _sha256_file(Path(source)),
                    "source": source,
                }
        included.append(record)

    catalog_rows: list[dict[str, str]] = []
    catalog_path: Path | None = None
    if candidates_path is not None:
        catalog_rows = build_factor_catalog(
            candidates_path,
            batch_manifest=batch_manifest,
            results_root=results_root,
        )
        catalog_path = write_factor_catalog(catalog_rows, package_root / "factor_catalog.csv")

    manifest: dict[str, Any] = {
        "package_id": package_root.name,
        "created_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "rule": "only factors with status == 'validated' are included; everything else is listed as excluded",
        "source": {
            "path": str(source_path),
            "sha256": _sha256_file(source_path) if source_path.is_file() else None,
        },
        "counts": {
            "included": len(included),
            "excluded": len(excluded),
            "total_seen": len(index),
        },
        "included_factors": included,
        "excluded_factors": excluded,
        "factor_catalog_csv": str(catalog_path) if catalog_path is not None else None,
        "factor_catalog_sha256": _sha256_file(catalog_path) if catalog_path is not None else None,
    }
    if not included:
        manifest["warning"] = (
            "no factor reached status 'validated'; this package contains no valid alpha factor"
        )
    manifest_path = package_root / "package_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {**manifest, "package_manifest_path": str(manifest_path)}
