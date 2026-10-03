from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from research_core.factor_lab.deterministic_validation import (
    PROJECT_ROOT,
    _canonical_json,
    _frame_hash,
    _git_commit,
    _json_safe,
    execute_validation,
    load_validation_config,
)
from research_core.factor_lab.panel_source import LocalPanel, load_validation_panel
from research_core.factor_lab.precomputed_factors import (
    PrecomputedFactorSet,
    load_precomputed_factors,
)

REQUIRED_CANDIDATE_COLUMNS = ("factor_id",)
SUMMARY_COLUMNS = (
    "factor_id",
    "status",
    "failed_gates",
    "reason",
    "rank_ic_mean_primary",
    "rank_ic_t_stat_primary",
    "coverage_mean",
    "net_annualized",
    "style_r2_mean",
    "retention",
    "result_hash",
    "params_hash",
    "result_path",
    "manifest_path",
    "report_path",
)


class BatchValidationError(ValueError):
    """Raised when a candidate list or batch run cannot be set up."""


@dataclass(frozen=True)
class Candidate:
    factor_id: str
    metadata: dict[str, str]


def load_candidate_list(path: str | Path) -> list[Candidate]:
    """Read candidate_list.csv. ``factor_id`` is required; other columns pass through."""
    candidates_path = Path(path)
    if not candidates_path.is_file():
        raise BatchValidationError(f"candidate list does not exist: {candidates_path}")
    try:
        frame = pd.read_csv(candidates_path, dtype=str, encoding="utf-8-sig", keep_default_na=False)
    except Exception as exc:
        raise BatchValidationError(f"cannot read candidate list: {candidates_path}") from exc
    if frame.empty:
        raise BatchValidationError("candidate list must contain at least one row")
    missing = [column for column in REQUIRED_CANDIDATE_COLUMNS if column not in frame.columns]
    if missing:
        raise BatchValidationError(
            f"candidate list is missing required columns: {', '.join(missing)}"
        )

    candidates: list[Candidate] = []
    seen: set[str] = set()
    for position, row in enumerate(frame.to_dict(orient="records"), start=2):
        factor_id = str(row.get("factor_id", "")).strip()
        if not factor_id:
            raise BatchValidationError(f"candidate list row {position} has an empty factor_id")
        if factor_id in seen:
            raise BatchValidationError(f"candidate list has a duplicate factor_id: {factor_id}")
        seen.add(factor_id)
        metadata = {str(key): str(value) for key, value in row.items() if str(key) != "factor_id"}
        candidates.append(Candidate(factor_id=factor_id, metadata=metadata))
    return candidates


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parameters_snapshot(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "split": config["split"],
        "forward_returns": config["forward_returns"],
        "gates": config["gates"],
        "portfolio": config["portfolio"],
        "perturbation": config["perturbation"],
        "statistics": config["statistics"],
        "release": config["release"],
        "data": {
            "provider": config["data"]["provider"],
            "universe": config["data"]["universe"],
            "frequency": config["data"]["frequency"],
            "adjust_type": config["data"]["adjust_type"],
            "minimum_listing_days": config["data"]["minimum_listing_days"],
        },
    }


def _first_failed_gate(result: dict[str, Any]) -> dict[str, Any] | None:
    failed = result.get("failed_gates") or []
    if not failed:
        return None
    for gate in result.get("gates") or []:
        if gate.get("name") == failed[0]:
            return gate
    return None


def _metrics_row(result: dict[str, Any], primary_horizon: int) -> dict[str, Any]:
    if result.get("status") == "train_only":
        rank_ic = (result.get("train_rank_ic") or {}).get(f"{primary_horizon}d", {})
        coverage = result.get("coverage", {})
        return {
            "rank_ic_mean_primary": rank_ic.get("mean"),
            "rank_ic_t_stat_primary": rank_ic.get("t_stat"),
            "coverage_mean": coverage.get("mean_daily_coverage"),
            "net_annualized": None,
            "style_r2_mean": None,
            "retention": None,
        }
    rank_ic = (result.get("rank_ic") or {}).get(f"{primary_horizon}d", {})
    coverage = None
    for gate in result.get("gates") or []:
        if gate.get("name") == "coverage":
            coverage = (gate.get("actual") or {}).get("mean_daily_coverage")
            break
    return {
        "rank_ic_mean_primary": rank_ic.get("mean"),
        "rank_ic_t_stat_primary": rank_ic.get("t_stat"),
        "coverage_mean": coverage,
        "net_annualized": (result.get("portfolio") or {}).get("net_annualized"),
        "style_r2_mean": (result.get("style") or {}).get("r2_mean"),
        "retention": (result.get("style") or {}).get("retention"),
    }


def _rejection_reason(result: dict[str, Any]) -> str:
    status = result.get("status")
    if status == "validated":
        return ""
    if status == "train_only":
        return ""
    if status == "needs_human":
        return str(result.get("reason", ""))
    gate = _first_failed_gate(result)
    if gate is not None:
        return (
            f"failed_gate={gate['name']} actual={_canonical_json(gate.get('actual'))} "
            f"threshold={_canonical_json(gate.get('threshold'))}"
        )
    return f"status={status}"


def _build_entry(
    *,
    factor_id: str,
    status: str,
    outcome: dict[str, Any],
    metadata: dict[str, str],
    primary_horizon: int,
) -> dict[str, Any]:
    """Read the written result artifact so the summary carries the real metrics."""
    artifacts = {
        "result": outcome["artifacts"]["result"],
        "manifest": outcome["artifacts"]["manifest"],
        "report": outcome["artifacts"]["report"],
    }
    payload = json.loads(Path(artifacts["result"]).read_text(encoding="utf-8"))
    return {
        "factor_id": factor_id,
        "status": status,
        "failed_gates": list(payload.get("failed_gates") or []),
        "reason": _rejection_reason(payload),
        "metadata": metadata,
        "metrics": _metrics_row(payload, primary_horizon),
        "result_hash": outcome["manifest"].get("result_hash"),
        "params_hash": outcome["manifest"].get("params_hash"),
        "artifacts": artifacts,
        "artifact_sha256": {
            name: _sha256_file(Path(path)) for name, path in artifacts.items() if Path(path).is_file()
        },
    }


def run_batch(
    candidates_path: str | Path,
    *,
    config_path: str | Path = PROJECT_ROOT / "configs" / "validation_gates.yaml",
    panel_file: str | Path,
    panel_sidecar: str | Path | None = None,
    factor_file: str | Path,
    factor_sidecar: str | Path | None = None,
    segment: str = "oos",
    output_dir: str | Path | None = None,
    factor_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Run every candidate factor, recording per-factor failures without stopping the batch."""
    config = load_validation_config(config_path)
    primary_horizon = int(config["forward_returns"]["primary_horizon"])
    candidates = load_candidate_list(candidates_path)
    if factor_ids is not None:
        wanted = [str(value) for value in factor_ids]
        candidates = [item for item in candidates if item.factor_id in set(wanted)]
        if not candidates:
            raise BatchValidationError("no candidate matched the requested factor ids")

    panel: LocalPanel = load_validation_panel(panel_file, sidecar_path=panel_sidecar)
    factor_set: PrecomputedFactorSet = load_precomputed_factors(factor_file, sidecar_path=factor_sidecar)

    split = config["split"]
    span_start, span_end = factor_set.coverage_span()
    required_start = pd.Timestamp(split["train_start"]).date()
    required_end = pd.Timestamp(split["oos_end"]).date()
    if span_start > required_start or span_end < required_end:
        raise BatchValidationError(
            "precomputed factor file does not cover the frozen train..oos range "
            f"(file {span_start}..{span_end}, required {required_start}..{required_end})"
        )

    if output_dir is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        output_dir = PROJECT_ROOT / config["output"]["root"] / "_batches" / stamp
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    panel_provenance = {
        "panel_file": panel.path.name,
        "panel_file_sha256": panel.sha256,
        "panel_price_basis": panel.price_basis,
    }
    panel_metadata = {
        "provider": "local_panel_parquet",
        "panel_file": panel.path.name,
        "panel_sha256": panel.sha256,
        "price_basis": panel.price_basis,
    }

    entries: list[dict[str, Any]] = []
    for candidate in candidates:
        factor_id = candidate.factor_id
        try:
            outcome = execute_validation(
                factor_id,
                config_path=config_path,
                panel=panel.frame,
                source_metadata=panel_metadata,
                precomputed=factor_set,
                segment=segment,
                extra_manifest=panel_provenance,
            )
        except Exception as exc:  # one bad factor must not stop the batch
            entries.append(
                {
                    "factor_id": factor_id,
                    "status": "error",
                    "failed_gates": [],
                    "reason": f"{type(exc).__name__}: {exc}",
                    "metadata": candidate.metadata,
                    "metrics": {},
                    "result_hash": None,
                    "params_hash": None,
                    "artifacts": {},
                    "artifact_sha256": {},
                }
            )
            continue

        status = str(outcome.get("status"))
        if status == "needs_human":
            entries.append(
                {
                    "factor_id": factor_id,
                    "status": "needs_human",
                    "failed_gates": [],
                    "reason": str(outcome.get("reason", "")),
                    "metadata": candidate.metadata,
                    "metrics": {},
                    "result_hash": None,
                    "params_hash": None,
                    "artifacts": {"needs_human": outcome.get("artifact")},
                    "artifact_sha256": {},
                }
            )
            continue

        entries.append(
            _build_entry(
                factor_id=factor_id,
                status=status,
                outcome=outcome,
                metadata=candidate.metadata,
                primary_horizon=primary_horizon,
            )
        )

    summary_path = output_root / "batch_summary.csv"
    with summary_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(SUMMARY_COLUMNS))
        writer.writeheader()
        for entry in entries:
            metrics = entry.get("metrics") or {}
            writer.writerow(
                {
                    "factor_id": entry["factor_id"],
                    "status": entry["status"],
                    "failed_gates": ";".join(entry.get("failed_gates") or []),
                    "reason": entry.get("reason", ""),
                    "rank_ic_mean_primary": _csv_value(metrics.get("rank_ic_mean_primary")),
                    "rank_ic_t_stat_primary": _csv_value(metrics.get("rank_ic_t_stat_primary")),
                    "coverage_mean": _csv_value(metrics.get("coverage_mean")),
                    "net_annualized": _csv_value(metrics.get("net_annualized")),
                    "style_r2_mean": _csv_value(metrics.get("style_r2_mean")),
                    "retention": _csv_value(metrics.get("retention")),
                    "result_hash": entry.get("result_hash") or "",
                    "params_hash": entry.get("params_hash") or "",
                    "result_path": (entry.get("artifacts") or {}).get("result", ""),
                    "manifest_path": (entry.get("artifacts") or {}).get("manifest", ""),
                    "report_path": (entry.get("artifacts") or {}).get("report", ""),
                }
            )

    counts = {"validated": 0, "rejected": 0, "train_only": 0, "needs_human": 0, "error": 0}
    for entry in entries:
        counts[entry["status"]] = counts.get(entry["status"], 0) + 1

    manifest = {
        "batch_id": output_root.name,
        "created_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "code_commit": _git_commit(),
        "segment": segment,
        "candidates_file": Path(candidates_path).name,
        "candidates_file_sha256": _sha256_file(Path(candidates_path)),
        "candidate_count": len(candidates),
        "factor_ids": [candidate.factor_id for candidate in candidates],
        "panel_file": panel.path.name,
        "panel_file_sha256": panel.sha256,
        "panel_price_basis": panel.price_basis,
        "data_snapshot_hash": _frame_hash(panel.frame),
        "factor_file": factor_set.path.name,
        "factor_file_sha256": factor_set.sha256,
        "factor_sidecar_data_start": factor_set.sidecar["data_start"],
        "factor_sidecar_data_end": factor_set.sidecar["data_end"],
        "configuration_file": Path(config_path).name,
        "configuration_sha256": _sha256_file(Path(config_path)),
        "parameters": _parameters_snapshot(config),
        "counts": counts,
        "validated": [entry["factor_id"] for entry in entries if entry["status"] == "validated"],
        "rejected": [entry["factor_id"] for entry in entries if entry["status"] == "rejected"],
        "errors": [entry["factor_id"] for entry in entries if entry["status"] == "error"],
        "needs_human": [entry["factor_id"] for entry in entries if entry["status"] == "needs_human"],
        "results": entries,
        "outputs": {
            "batch_summary_csv": str(summary_path),
            "batch_summary_sha256": _sha256_file(summary_path),
        },
    }
    manifest_path = output_root / "batch_manifest.json"
    manifest_path.write_text(
        json.dumps(_json_safe(manifest, precision=int(config["output"]["float_precision"])), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    return {**manifest, "batch_manifest_path": str(manifest_path)}


def _csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.10g}"
    return str(value)
