from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from research_core.factor_lab.batch_validation import (
    _rejection_reason,
    load_candidate_list,
)

CATALOG_COLUMNS = (
    "factor_id",
    "name",
    "formula",
    "category",
    "required_fields",
    "direction",
    "status",
    "failed_gates",
    "reason",
    "result_hash",
    "evidence",
)
METADATA_COLUMNS = ("name", "formula", "category", "required_fields", "direction")
STATUS_NOT_RUN = "not_run"


class FactorCatalogError(ValueError):
    """Raised when a factor catalog cannot be built from the given inputs."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _entry_from_result_files(factor_dir: Path) -> dict[str, Any] | None:
    result_path = factor_dir / "validation_result.json"
    manifest_path = factor_dir / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    if not result_path.is_file():
        needs_human_path = factor_dir / "needs_human.json"
        if not needs_human_path.is_file():
            return None
        payload = json.loads(needs_human_path.read_text(encoding="utf-8"))
        return {
            "status": "needs_human",
            "failed_gates": [],
            "reason": str(payload.get("reason", "")),
            "result_hash": None,
            "evidence": str(needs_human_path),
            "artifacts": {"needs_human": str(needs_human_path)},
        }
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    return {
        "status": str(payload.get("status", STATUS_NOT_RUN)),
        "failed_gates": list(payload.get("failed_gates") or []),
        "reason": _rejection_reason(payload),
        "result_hash": manifest.get("result_hash"),
        "evidence": str(manifest_path if manifest_path.is_file() else result_path),
        "artifacts": {
            "report": str(factor_dir / "validation_report.md"),
            "result": str(result_path),
            "manifest": str(manifest_path),
        },
    }


def index_from_results_root(results_root: str | Path) -> dict[str, dict[str, Any]]:
    """Read per-factor artifacts written by ``validate`` / ``validate-batch``."""
    root = Path(results_root)
    if not root.is_dir():
        raise FactorCatalogError(f"results root is not a directory: {root}")
    index: dict[str, dict[str, Any]] = {}
    for factor_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        entry = _entry_from_result_files(factor_dir)
        if entry is not None:
            index[factor_dir.name] = entry
    return index


def index_from_batch_manifest(batch_manifest: str | Path) -> dict[str, dict[str, Any]]:
    """Read the per-factor verdicts recorded by ``validate-batch``."""
    path = Path(batch_manifest)
    if not path.is_file():
        raise FactorCatalogError(f"batch manifest does not exist: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    results = payload.get("results")
    if not isinstance(results, list):
        raise FactorCatalogError("batch manifest has no results list")
    index: dict[str, dict[str, Any]] = {}
    for entry in results:
        factor_id = str(entry.get("factor_id", ""))
        if not factor_id:
            continue
        index[factor_id] = {
            "status": str(entry.get("status", STATUS_NOT_RUN)),
            "failed_gates": list(entry.get("failed_gates") or []),
            "reason": str(entry.get("reason", "")),
            "result_hash": entry.get("result_hash"),
            "evidence": str(path),
            "artifacts": dict(entry.get("artifacts") or {}),
        }
    return index


def build_factor_catalog(
    candidates_path: str | Path,
    *,
    batch_manifest: str | Path | None = None,
    results_root: str | Path | None = None,
) -> list[dict[str, str]]:
    """Build the delivery catalog: metadata from the candidate list, status from real runs.

    Anything that was never run is reported as ``not_run``. Metadata that the candidate list
    does not carry stays empty; this function never invents a formula, direction or status.
    """
    if batch_manifest is not None and results_root is not None:
        raise FactorCatalogError("pass either batch_manifest or results_root, not both")
    candidates = load_candidate_list(candidates_path)
    if batch_manifest is not None:
        index = index_from_batch_manifest(batch_manifest)
    elif results_root is not None:
        index = index_from_results_root(results_root)
    else:
        index = {}

    rows: list[dict[str, str]] = []
    for candidate in candidates:
        entry = index.get(candidate.factor_id)
        row = {"factor_id": candidate.factor_id}
        for column in METADATA_COLUMNS:
            row[column] = candidate.metadata.get(column, "")
        if entry is None:
            row.update(
                {
                    "status": STATUS_NOT_RUN,
                    "failed_gates": "",
                    "reason": "no validation result found for this factor",
                    "result_hash": "",
                    "evidence": "",
                }
            )
        else:
            row.update(
                {
                    "status": entry["status"],
                    "failed_gates": ";".join(entry["failed_gates"]),
                    "reason": entry["reason"],
                    "result_hash": entry.get("result_hash") or "",
                    "evidence": entry.get("evidence", ""),
                }
            )
        rows.append({column: row.get(column, "") for column in CATALOG_COLUMNS})
    return rows


def write_factor_catalog(rows: list[dict[str, str]], path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(CATALOG_COLUMNS))
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return target
