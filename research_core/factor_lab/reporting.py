from __future__ import annotations

from typing import Any

from research_core.factor_lab.runtime import now_iso


def build_alpha101_research_report(
    *,
    job_id: str,
    factor_names: list[str],
    evaluation_report: dict[str, Any],
    proof_payloads: dict[str, dict[str, Any]],
    truth_payloads: dict[str, dict[str, Any]],
    data_source: str,
) -> dict[str, Any]:
    proof_summary: list[dict[str, Any]] = []
    proof_status_counts: dict[str, int] = {}
    truth_status_counts: dict[str, int] = {}
    passed_factors: list[str] = []
    partial_factors: list[str] = []
    failed_factors: list[str] = []
    truth_exact_match_factors: list[str] = []
    truth_blocker_factors: list[str] = []
    truth_missing_factors: list[str] = []
    for factor_name in factor_names:
        proof = proof_payloads[factor_name]
        truth = truth_payloads.get(factor_name, {})
        metrics = evaluation_report["summary"]["metrics"][factor_name]
        proof_status = proof["status"]
        truth_status = _resolve_truth_status(truth)
        proof_status_counts[proof_status] = proof_status_counts.get(proof_status, 0) + 1
        truth_status_counts[truth_status] = truth_status_counts.get(truth_status, 0) + 1
        if proof_status == "passed":
            passed_factors.append(factor_name)
        elif proof_status == "failed":
            failed_factors.append(factor_name)
        else:
            partial_factors.append(factor_name)
        if truth_status == "exact_match":
            truth_exact_match_factors.append(factor_name)
        elif truth_status in {"mismatch", "empty_compare"}:
            truth_blocker_factors.append(factor_name)
        elif truth_status == "not_compared":
            truth_missing_factors.append(factor_name)
        proof_summary.append(
            {
                "factor_name": factor_name,
                "proof_status": proof_status,
                "truth_status": truth_status,
                "coverage_ratio": metrics["coverage_ratio"],
                "rank_ic_mean": metrics["rank_ic_mean"],
                "rank_ic_ir": metrics["rank_ic_ir"],
                "long_short_mean": metrics["long_short_mean"],
                "truth_compared_count": truth.get("compared_count", 0),
                "truth_exact_match_ratio": truth.get("exact_match_ratio"),
                "truth_max_abs_error": truth.get("max_abs_error"),
            }
        )
    overall_status = _resolve_overall_status(proof_status_counts, truth_enabled=bool(truth_payloads))
    return {
        "job_id": job_id,
        "library": "Alpha101",
        "generated_at": now_iso(),
        "data_source": data_source,
        "dataset": evaluation_report["dataset"],
        "factor_count": len(factor_names),
        "summary": {
            "overall_status": overall_status,
            "ready_for_official_proof": overall_status == "passed",
            "proof_status_counts": proof_status_counts,
            "truth_status_counts": truth_status_counts,
            "truth_enabled": bool(truth_payloads),
            "passed_factors": _sort_factor_names(passed_factors),
            "partial_factors": _sort_factor_names(partial_factors),
            "failed_factors": _sort_factor_names(failed_factors),
            "truth_exact_match_factors": _sort_factor_names(truth_exact_match_factors),
            "truth_blocker_factors": _sort_factor_names(truth_blocker_factors),
            "truth_missing_factors": _sort_factor_names(truth_missing_factors),
        },
        "factors": proof_summary,
    }


def render_alpha101_research_report_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Alpha101 Research Proof Report",
        "",
        f"- Job ID: {report['job_id']}",
        f"- Generated at: {report['generated_at']}",
        f"- Data source: {report['data_source']}",
        f"- Dataset rows: {report['dataset']['rows']}",
        f"- Securities: {report['dataset']['codes']}",
        f"- Dates: {report['dataset']['dates']}",
        f"- Overall status: {report['summary']['overall_status']}",
        f"- Ready for official proof: {report['summary']['ready_for_official_proof']}",
        f"- Proof status counts: {_format_counts(report['summary']['proof_status_counts'])}",
        f"- Truth status counts: {_format_counts(report['summary']['truth_status_counts'])}",
        f"- Failed factors: {_format_factor_list(report['summary']['failed_factors'])}",
        f"- Partial factors: {_format_factor_list(report['summary']['partial_factors'])}",
        f"- Truth blockers: {_format_factor_list(report['summary']['truth_blocker_factors'])}",
        f"- Truth missing: {_format_factor_list(report['summary']['truth_missing_factors'])}",
        "",
        "| Factor | Proof | Truth | Coverage | Rank IC Mean | Rank IC IR | Long-Short Mean | Truth Match | Max Abs Error |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for item in report["factors"]:
        truth_match = item["truth_exact_match_ratio"]
        max_abs_error = item["truth_max_abs_error"]
        lines.append(
            f"| {item['factor_name']} | {item['proof_status']} | {item['truth_status']} | {item['coverage_ratio']:.4f} | "
            f"{item['rank_ic_mean']:.6f} | {item['rank_ic_ir']:.6f} | {item['long_short_mean']:.6f} | "
            f"{_format_optional_float(truth_match)} | {_format_optional_float(max_abs_error)} |"
        )
    return "\n".join(lines) + "\n"


def _format_optional_float(value: Any) -> str:
    if value is None:
        return "-"
    try:
        value = float(value)
    except (TypeError, ValueError):
        return "-"
    if value != value:
        return "-"
    return f"{value:.6f}"


def _resolve_truth_status(truth_payload: dict[str, Any]) -> str:
    if not truth_payload:
        return "not_compared"
    compared_count = int(truth_payload.get("compared_count", 0))
    mismatch_count = int(truth_payload.get("mismatch_count", 0))
    if compared_count <= 0:
        return "empty_compare"
    if mismatch_count == 0:
        return "exact_match"
    return "mismatch"


def _format_counts(counts: dict[str, int]) -> str:
    if not counts:
        return "-"
    return ", ".join(f"{key}={counts[key]}" for key in sorted(counts))


def _resolve_overall_status(proof_status_counts: dict[str, int], *, truth_enabled: bool) -> str:
    if proof_status_counts.get("failed", 0) > 0:
        return "failed"
    if not truth_enabled:
        return "partial"
    if proof_status_counts.get("partial", 0) > 0 or proof_status_counts.get("pending", 0) > 0:
        return "partial"
    if proof_status_counts.get("passed", 0) > 0:
        return "passed"
    return "pending"


def _format_factor_list(factor_names: list[str], limit: int = 12) -> str:
    if not factor_names:
        return "-"
    if len(factor_names) <= limit:
        return ", ".join(factor_names)
    head = ", ".join(factor_names[:limit])
    return f"{head}, ... (+{len(factor_names) - limit})"


def _sort_factor_names(factor_names: list[str]) -> list[str]:
    def _key(name: str) -> tuple[int, str]:
        suffix = name.replace("alpha", "", 1)
        return (int(suffix), name) if suffix.isdigit() else (10**9, name)

    return sorted(factor_names, key=_key)
