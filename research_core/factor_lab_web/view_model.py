from __future__ import annotations

from typing import Any

from research_core.factor_lab import FactorLabWorkspaceConfig, get_factor_lab_job
from research_core.factor_lab.runtime import now_iso
from research_core.factor_lab_web.artifact_service import list_job_artifacts
from research_core.factor_lab_web.factor_sources import collect_factor_specs_with_diagnostics
from research_core.factor_lab_web.repository import latest_factor_reports_with_diagnostics, safe_float, sort_factor_key


SCHEMA_VERSION = "factor_lab_view_v1"


def build_factor_library_view(config: FactorLabWorkspaceConfig | None = None) -> dict[str, Any]:
    workspace = config or FactorLabWorkspaceConfig()
    metrics_by_factor, artifact_diagnostics = latest_factor_reports_with_diagnostics(workspace)

    discovered, source_diagnostics = _discover_factors()
    diagnostics = [*source_diagnostics, *artifact_diagnostics]
    factors = [
        _factor_row(
            spec=spec,
            metrics_by_factor=metrics_by_factor,
        )
        for spec in discovered.values()
    ]

    factors = sorted(factors, key=sort_factor_key)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now_iso(),
        "local_flask": {"connected": True},
        "cloud_registry": {"status": "not_synced", "label": "未同步"},
        "categories": _category_counts(factors),
        "libraries": _library_counts(factors),
        "metadata": {
            "factor_source_warning_count": len(source_diagnostics),
            "artifact_warning_count": len(artifact_diagnostics),
            "warning_count": len(diagnostics),
            "factor_source_types": sorted({str(factor.get("source")) for factor in factors if factor.get("source")}),
        },
        "errors": _diagnostic_errors(diagnostics),
        "factors": factors,
    }


def build_factor_view(
    factor_id: str,
    config: FactorLabWorkspaceConfig | None = None,
) -> dict[str, Any] | None:
    workspace = config or FactorLabWorkspaceConfig()
    library, factor_name = _parse_factor_id(factor_id)
    library = _display_library(library)
    library_view = build_factor_library_view(workspace)
    row = next(
        (
            factor
            for factor in library_view["factors"]
            if factor["library"] == library and factor["raw_factor_name"] == factor_name
        ),
        None,
    )
    if row is None:
        return None

    job = get_factor_lab_job(str(row.get("latest_job_id")), workspace) if row.get("latest_job_id") else None
    artifacts = (
        list_job_artifacts(
            str(row["latest_job_id"]),
            factor_name=row["raw_factor_name"],
            workspace=workspace,
        )
        if row.get("latest_job_id")
        else []
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now_iso(),
        "factor": {
            "factor_id": row["id"],
            "factor_name": row["factor_name"],
            "raw_factor_name": row["raw_factor_name"],
            "library": row["library"],
            "category": row["category"],
            "category_inferred": row.get("category_inferred", False),
            "subcategory": row["subcategory"],
            "required_fields": row.get("required_fields", []),
            "metadata": row.get("metadata", {}),
        },
        "job": {
            "job_id": row.get("latest_job_id"),
            "status": (job or {}).get("status"),
            "library": (job or {}).get("library"),
            "generated_at": row.get("latest_checked_at") or (job or {}).get("generated_at"),
            "data_source": row.get("data_source") or (job or {}).get("data_source"),
            "truth_enabled": (job or {}).get("truth_enabled"),
            "dataset": (job or {}).get("dataset", {}),
        },
        "validation": {
            "proof_status": row.get("proof_status"),
            "truth_status": row.get("truth_status"),
            "overall_status": row.get("overall_status"),
            "truth_exact_match_ratio": row.get("truth_exact_match_ratio"),
            "truth_max_abs_error": row.get("truth_max_abs_error"),
        },
        "metrics": {
            "coverage_ratio": row.get("coverage_ratio"),
            "rank_ic_mean": row.get("rank_ic_mean"),
            "rank_ic_ir": row.get("rank_ic_ir"),
            "long_short_mean": row.get("long_short_mean"),
        },
        "research": build_research_analysis_view(factor_id, config=workspace),
        "artifacts": _annotate_artifacts(artifacts, row),
        "errors": _factor_errors(row),
        "metadata": {
            "view_source": "factor_lab_web_adapter",
            "data_source": row.get("data_source"),
            "display_library_alias": "WQ101 maps to the current Alpha101 implementation.",
            "factor_source_warning_count": library_view.get("metadata", {}).get("factor_source_warning_count", 0),
            "artifact_warning_count": library_view.get("metadata", {}).get("artifact_warning_count", 0),
            "warning_count": library_view.get("metadata", {}).get("warning_count", 0),
        },
    }


def build_research_analysis_view(
    factor_id: str,
    config: FactorLabWorkspaceConfig | None = None,
) -> dict[str, Any]:
    return {
        "status": "not_available",
        "reason": "waiting_for_research_analysis_backend",
        "is_placeholder": True,
        "factor_id": factor_id,
        "params": {},
        "ic_summary": None,
        "ic_series": [],
        "stratification_curves": [],
        "group_performance": [],
    }


def _factor_row(
    *,
    spec: dict[str, Any],
    metrics_by_factor: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    library = str(spec.get("library") or "User Custom")
    raw_library = str(spec.get("raw_library") or library)
    raw_factor_name = str(spec.get("factor_name") or "")
    factor_name = _display_factor_name(library, raw_factor_name, spec)
    required_fields = list(spec.get("required_fields") or [])
    metrics = _find_metrics(metrics_by_factor, raw_factor_name, [raw_library, library, *spec.get("metric_libraries", [])])
    proof_status = str(metrics.get("proof_status") or "missing")
    truth_status = str(metrics.get("truth_status") or "not_compared")
    overall_status = _factor_overall_status(proof_status, truth_status)
    category, category_inferred = _category_from_spec(spec, required_fields)
    metadata = dict(spec.get("metadata") or {})
    metadata["category_inferred"] = category_inferred
    return {
        "id": f"{library}:{raw_factor_name}",
        "factor_name": factor_name,
        "raw_factor_name": raw_factor_name,
        "library": library,
        "raw_library": raw_library,
        "category": category,
        "category_inferred": category_inferred,
        "subcategory": str(spec.get("subcategory") or _subcategory_from_fields(required_fields)),
        "required_fields": required_fields,
        "metadata": metadata,
        "formula": spec.get("formula") or "",
        "description": spec.get("description") or "",
        "source_document": spec.get("source_document") or "",
        "source": spec.get("source") or "",
        "source_id": spec.get("source_id") or "",
        "display_name": spec.get("display_name") or factor_name,
        "declared_factor_id": spec.get("factor_id") or "",
        "implementation_status": spec.get("implementation_status") or spec.get("status") or "unknown",
        "proof_status": proof_status,
        "truth_status": truth_status,
        "overall_status": overall_status,
        "coverage_ratio": safe_float(metrics.get("coverage_ratio")),
        "rank_ic_mean": safe_float(metrics.get("rank_ic_mean")),
        "rank_ic_ir": safe_float(metrics.get("rank_ic_ir")),
        "long_short_mean": safe_float(metrics.get("long_short_mean")),
        "truth_exact_match_ratio": safe_float(metrics.get("truth_exact_match_ratio")),
        "truth_max_abs_error": safe_float(metrics.get("truth_max_abs_error")),
        "latest_job_id": metrics.get("latest_job_id"),
        "latest_checked_at": metrics.get("latest_checked_at"),
        "data_source": metrics.get("data_source"),
        "dataset": metrics.get("dataset", {}),
        "reuse_recommendation": _reuse_recommendation(proof_status, truth_status),
    }


def _discover_factors() -> tuple[dict[tuple[str, str], dict[str, Any]], list[dict[str, str]]]:
    factors: dict[tuple[str, str], dict[str, Any]] = {}
    specs, source_diagnostics = collect_factor_specs_with_diagnostics()

    for spec in specs:
        _merge_factor(factors, spec)

    return factors, source_diagnostics


def _merge_factor(factors: dict[tuple[str, str], dict[str, Any]], spec: dict[str, Any]) -> None:
    factor_name = str(spec.get("factor_name") or "")
    if not factor_name:
        return
    library = _display_library(str(spec.get("library") or spec.get("raw_library") or "User Custom"))
    key = (library, factor_name)
    existing = factors.get(key, {})
    metric_libraries = set(existing.get("metric_libraries", []))
    metric_libraries.update(spec.get("metric_libraries", []))
    if spec.get("raw_library"):
        metric_libraries.add(str(spec["raw_library"]))
    factors[key] = {
        **existing,
        **{k: v for k, v in spec.items() if v not in (None, "", [])},
        "library": library,
        "metric_libraries": sorted(metric_libraries),
    }


def _display_library(library: str) -> str:
    normalized = library.lower()
    if normalized == "alpha101":
        return "WQ101"
    if normalized in {"gtja191", "alpha191"}:
        return "GTJA191"
    if normalized in {"quantapi33", "quantapi", "quant_api", "quant api"}:
        return "QuantAPI"
    if not library:
        return "User Custom"
    return library


def _display_factor_name(library: str, factor_name: str, spec: dict[str, Any]) -> str:
    factor_id = str(spec.get("factor_id") or "")
    if library == "GTJA191" and factor_id:
        return factor_id
    return factor_name


def _find_metrics(
    metrics_by_factor: dict[tuple[str, str], dict[str, Any]],
    factor_name: str,
    libraries: list[str],
) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for library in libraries:
        if (library, factor_name) in metrics_by_factor:
            candidates.append(metrics_by_factor[(library, factor_name)])
    if not candidates:
        return {}
    return max(candidates, key=lambda item: str(item.get("latest_checked_at") or ""))


def _category_counts(factors: list[dict[str, Any]]) -> dict[str, int]:
    labels = ["全部", "量价因子", "技术因子", "财务因子", "规模因子", "价值因子", "自定义因子"]
    counts = {label: 0 for label in labels}
    counts["全部"] = len(factors)
    for factor in factors:
        category = str(factor.get("category") or "自定义因子")
        counts[category] = counts.get(category, 0) + 1
    return counts


def _library_counts(factors: list[dict[str, Any]]) -> dict[str, int]:
    labels = ["WQ101", "GTJA191", "TA-Lib", "User Custom"]
    counts = {label: 0 for label in labels}
    for factor in factors:
        library = str(factor.get("library") or "User Custom")
        counts[library] = counts.get(library, 0) + 1
    return counts


def _subcategory_from_fields(required_fields: list[str]) -> str:
    fields = {field.lower() for field in required_fields}
    if {"volume", "amount", "vwap"} & fields:
        return "成交量"
    if {"returns", "close", "open"} & fields:
        return "动量"
    if {"high", "low"} & fields:
        return "波动率"
    return "价量相关"


def _category_from_spec(spec: dict[str, Any], required_fields: list[str]) -> tuple[str, bool]:
    explicit = spec.get("category") or spec.get("factor_category")
    if explicit:
        return str(explicit), False

    tags = {str(tag).lower() for tag in spec.get("tags", [])}
    fields = {field.lower() for field in required_fields}
    library = str(spec.get("library") or "").lower()

    if library in {"wq101", "gtja191", "ta-lib", "talib"}:
        return "量价因子", True
    if {"alpha101", "worldquant", "formulaic-alpha", "gtja191"} & tags:
        return "量价因子", True
    if {"open", "close", "high", "low", "volume", "amount", "vwap", "returns"} & fields:
        return "量价因子", True
    if {"finance", "fundamental", "financial"} & tags:
        return "财务因子", True
    if {"size", "market_cap", "scale"} & tags:
        return "规模因子", True
    if {"value", "valuation"} & tags:
        return "价值因子", True
    if {"technical", "indicator"} & tags:
        return "技术因子", True
    return "自定义因子", True


def _reuse_recommendation(proof_status: str, truth_status: str) -> str:
    if proof_status == "passed" and truth_status == "exact_match":
        return "可复用"
    if proof_status in {"failed", "partial"} or truth_status == "mismatch":
        return "建议重跑"
    if proof_status == "missing":
        return "未复现"
    return "待确认"


def _factor_overall_status(proof_status: str, truth_status: str) -> str:
    proof = str(proof_status or "").lower()
    truth = str(truth_status or "").lower()

    if proof == "failed":
        return "failed"
    if proof == "partial":
        return "partial"
    if proof in {"missing", "pending", ""}:
        return "pending"
    if truth in {"mismatch", "empty_compare", "missing"}:
        return "review_needed"
    if proof == "passed" and truth in {"exact_match", "not_applicable"}:
        return "passed"
    if truth in {"not_compared", "pending", ""}:
        return "pending"
    return "review_needed"


def _parse_factor_id(factor_id: str) -> tuple[str, str]:
    if ":" not in factor_id:
        return "WQ101", factor_id
    library, factor_name = factor_id.split(":", 1)
    return library, factor_name


def _annotate_artifacts(artifacts: list[dict[str, Any]], factor: dict[str, Any]) -> list[dict[str, Any]]:
    annotated: list[dict[str, Any]] = []
    for artifact in artifacts:
        kind = artifact["kind"]
        validation_status = "generated"
        if kind == "proof":
            validation_status = str(factor.get("proof_status") or "missing")
        elif kind in {"truth_compare", "evaluation_json"}:
            validation_status = str(factor.get("truth_status") or "not_compared")
        annotated.append({**artifact, "validation_status": validation_status})
    return annotated


def _factor_errors(factor: dict[str, Any]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    if factor.get("proof_status") in {"failed", "partial"}:
        errors.append({"code": "PROOF_NOT_PASSED", "status": factor.get("proof_status")})
    if factor.get("truth_status") in {"mismatch", "empty_compare"}:
        errors.append({"code": "TRUTH_NOT_EXACT_MATCH", "status": factor.get("truth_status")})
    return errors


def _diagnostic_errors(diagnostics: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        {
            "code": _diagnostic_code(diagnostic),
            "level": diagnostic.get("level", "warning"),
            "source_type": diagnostic.get("source_type", ""),
            "source_id": diagnostic.get("source_id", ""),
            "message": diagnostic.get("message", ""),
        }
        for diagnostic in diagnostics
    ]


def _diagnostic_code(diagnostic: dict[str, str]) -> str:
    if diagnostic.get("source_type") == "specs_py":
        return "FACTOR_SOURCE_WARNING"
    return "ARTIFACT_WARNING"
