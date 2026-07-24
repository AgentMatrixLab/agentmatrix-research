from __future__ import annotations

import json
import logging
import math
import re
from pathlib import Path
from typing import Any

from research_core.factor_lab import FactorLabWorkspaceConfig, list_factor_lab_jobs


LOGGER = logging.getLogger(__name__)


def read_json(
    path: str | Path | None,
    *,
    diagnostics: list[dict[str, str]] | None = None,
    source_type: str = "runtime_artifact",
) -> dict[str, Any] | None:
    if not path:
        return None
    target = Path(path)
    if not target.exists():
        return None
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except OSError as exc:
        _warn_json_read(diagnostics, source_type, target, f"cannot read JSON artifact: {exc}")
        return None
    except json.JSONDecodeError as exc:
        _warn_json_read(diagnostics, source_type, target, f"invalid JSON artifact: {exc}")
        return None
    if not isinstance(payload, dict):
        _warn_json_read(diagnostics, source_type, target, f"JSON artifact root is {type(payload).__name__}, expected object")
        return None
    return payload


def _warn_json_read(
    diagnostics: list[dict[str, str]] | None,
    source_type: str,
    path: Path,
    message: str,
) -> None:
    source_id = str(path)
    if diagnostics is not None:
        diagnostics.append(
            {
                "level": "warning",
                "source_type": source_type,
                "source_id": source_id,
                "message": message,
            }
        )
    LOGGER.warning("Factor Lab artifact warning in %s: %s", source_id, message)


def safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def factor_number(factor_name: str) -> int | None:
    match = re.search(r"(\d+)$", factor_name.lower())
    return int(match.group(1)) if match else None


def sort_factor_key(item: dict[str, Any]) -> tuple[str, int, str]:
    library_order = {
        "WQ101": "00",
        "Alpha101": "00",
        "GTJA191": "01",
        "TA-Lib": "02",
        "User Custom": "99",
    }
    library = str(item.get("library", ""))
    return (
        library_order.get(library, f"50:{library}"),
        factor_number(str(item.get("raw_factor_name", ""))) or 10**9,
        str(item.get("factor_name", "")),
    )


def latest_factor_reports(
    workspace: FactorLabWorkspaceConfig,
) -> dict[tuple[str, str], dict[str, Any]]:
    reports, _diagnostics = latest_factor_reports_with_diagnostics(workspace)
    return reports


def latest_factor_reports_with_diagnostics(
    workspace: FactorLabWorkspaceConfig,
) -> tuple[dict[tuple[str, str], dict[str, Any]], list[dict[str, str]]]:
    reports: dict[tuple[str, str], dict[str, Any]] = {}
    diagnostics: list[dict[str, str]] = []
    jobs = list_factor_lab_jobs(workspace)
    for job in sorted(jobs, key=lambda item: item.get("generated_at", ""), reverse=True):
        if job.get("data_source") == "quant_api":
            for key, payload in _real_job_factor_reports(job, diagnostics).items():
                if key not in reports:
                    reports[key] = payload
            continue

        report_path = job.get("artifacts", {}).get("research_report_json")
        report = read_json(report_path, diagnostics=diagnostics, source_type="proof_report_json")
        if not report:
            continue
        library = str(report.get("library") or job.get("library") or "")
        for factor in report.get("factors", []):
            raw_factor_name = str(factor.get("factor_name", ""))
            key = (library, raw_factor_name)
            if key in reports:
                continue
            reports[key] = {
                **factor,
                "latest_job_id": report.get("job_id") or job.get("job_id"),
                "latest_checked_at": report.get("generated_at") or job.get("generated_at"),
                "data_source": report.get("data_source") or job.get("data_source"),
                "dataset": report.get("dataset") or job.get("dataset") or {},
            }
    for key, payload in _factor_detail_cache_reports(workspace, diagnostics).items():
        existing = reports.get(key)
        if existing is None or _report_timestamp(payload) > _report_timestamp(existing):
            reports[key] = payload
    return reports, diagnostics


def _real_job_factor_reports(
    job: dict[str, Any],
    diagnostics: list[dict[str, str]],
) -> dict[tuple[str, str], dict[str, Any]]:
    artifacts = job.get("artifacts", {})
    evaluation = read_json(
        artifacts.get("evaluation_json"),
        diagnostics=diagnostics,
        source_type="real_evaluation_json",
    )
    strategy = read_json(
        artifacts.get("strategy_json"),
        diagnostics=diagnostics,
        source_type="real_strategy_json",
    )
    if not evaluation:
        return {}

    library = str(evaluation.get("library") or job.get("library") or "")
    metrics_by_factor = evaluation.get("summary", {}).get("metrics", {})
    strategy_by_factor = (strategy or {}).get("factors", {})
    reports: dict[tuple[str, str], dict[str, Any]] = {}
    for factor_name, metrics in metrics_by_factor.items():
        if not isinstance(metrics, dict):
            continue
        factor_strategy = strategy_by_factor.get(factor_name, {})
        strategy_summary = factor_strategy.get("summary", {}) if isinstance(factor_strategy, dict) else {}
        reports[(library, str(factor_name))] = {
            "factor_name": factor_name,
            "proof_status": "passed",
            "truth_status": "not_applicable",
            "coverage_ratio": metrics.get("coverage_ratio"),
            "rank_ic_mean": metrics.get("rank_ic_mean"),
            "rank_ic_ir": metrics.get("rank_ic_ir"),
            "long_short_mean": metrics.get("long_short_mean"),
            "latest_job_id": job.get("job_id"),
            "latest_checked_at": job.get("generated_at"),
            "data_source": job.get("data_source"),
            "dataset": job.get("dataset") or evaluation.get("dataset") or {},
            "strategy": strategy_summary,
        }
    return reports


def _factor_detail_cache_reports(
    workspace: FactorLabWorkspaceConfig,
    diagnostics: list[dict[str, str]],
) -> dict[tuple[str, str], dict[str, Any]]:
    cache_dir = workspace.runtime_root / "factor_detail_cache"
    if not cache_dir.is_dir():
        return {}

    reports: dict[tuple[str, str], dict[str, Any]] = {}
    for path in sorted(cache_dir.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        payload = read_json(path, diagnostics=diagnostics, source_type="factor_detail_cache")
        if not payload:
            continue
        library = str(payload.get("library") or _library_from_factor_id(str(payload.get("factor_id") or "")))
        factor_name = str(payload.get("factor_name") or _factor_name_from_factor_id(str(payload.get("factor_id") or "")))
        if not library or not factor_name:
            continue
        generated_at = str(payload.get("artifact_cache", {}).get("generated_at") or "")
        reports[(library, factor_name)] = {
            "factor_name": factor_name,
            "proof_status": "passed",
            "truth_status": "not_applicable",
            "coverage_ratio": payload.get("coverage_ratio"),
            "rank_ic_mean": payload.get("rank_ic_mean"),
            "rank_ic_ir": payload.get("rank_ic_ir"),
            "long_short_mean": payload.get("long_short_mean"),
            "latest_job_id": payload.get("job_id") or f"factor_detail_cache:{library}:{factor_name}",
            "latest_checked_at": generated_at,
            "data_source": payload.get("data_source"),
            "dataset": payload.get("dataset") or {},
        }
    return reports


def _library_from_factor_id(factor_id: str) -> str:
    return factor_id.split(":", 1)[0] if ":" in factor_id else ""


def _factor_name_from_factor_id(factor_id: str) -> str:
    return factor_id.split(":", 1)[1] if ":" in factor_id else ""


def _report_timestamp(report: dict[str, Any]) -> str:
    return str(report.get("latest_checked_at") or "")
