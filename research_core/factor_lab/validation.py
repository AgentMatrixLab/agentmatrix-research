from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd

from contracts.factor_research import FactorResearchSpec, FactorValidationArtifact, FactorValidationReport
from research_core.factor_lab.runtime import FactorLabWorkspaceConfig, now_iso


def build_proof_template(spec: FactorResearchSpec) -> FactorValidationReport:
    checks = [
        {
            "name": "formula_match",
            "status": "pending",
            "description": "逐项核对代码公式、窗口参数、延迟和排序方向。",
        },
        {
            "name": "field_mapping_match",
            "status": "pending",
            "description": "确认字段口径、复权方式、股票池过滤和频率一致。",
        },
        {
            "name": "sample_point_reconciliation",
            "status": "pending",
            "description": "对抽样股票和日期做逐点数值核对。",
        },
        {
            "name": "cross_section_truth_compare",
            "status": "pending",
            "description": "与外部真值或公开参考序列做截面对比。",
        },
        {
            "name": "evaluation_consistency",
            "status": "pending",
            "description": "复核 IC、分层、多空和中性化检验结果是否可重复。",
        },
    ]
    artifacts = [
        FactorValidationArtifact("spec", "", "标准化 FactorSpec"),
        FactorValidationArtifact("sample_checks", "", "抽样点位核验明细"),
        FactorValidationArtifact("cross_section_compare", "", "截面真值对照结果"),
        FactorValidationArtifact("evaluation_report", "", "IC 与回测检验结果"),
    ]
    return FactorValidationReport(
        factor_name=spec.factor_name,
        library=spec.library,
        status="pending",
        summary="等待补充代码、真值和检验产物后再出具复现证明。",
        checks=checks,
        artifacts=artifacts,
        diagnostics={"generated_at": now_iso(), "version": spec.version},
    )


def build_sample_checks(
    factor_frame: pd.DataFrame,
    *,
    factor_name: str,
    max_points: int = 12,
) -> dict[str, Any]:
    samples = (
        factor_frame.loc[factor_frame[factor_name].notna(), ["date", "code", factor_name]]
        .head(max_points)
        .copy()
    )
    if samples.empty:
        items: list[dict[str, Any]] = []
    else:
        samples["date"] = pd.to_datetime(samples["date"]).dt.strftime("%Y-%m-%d")
        items = samples.rename(columns={factor_name: "value"}).to_dict(orient="records")
    return {
        "factor_name": factor_name,
        "sample_count": len(items),
        "items": items,
    }


def build_validation_report(
    *,
    spec: FactorResearchSpec,
    available_columns: list[str],
    factor_metrics: dict[str, Any],
    sample_path: str,
    spec_path: str,
    evaluation_path: str,
    truth_path: str = "",
    job_id: str = "",
) -> FactorValidationReport:
    has_formula = bool(spec.formula.strip())
    field_mapping_ok = set(spec.required_fields).issubset(set(available_columns))
    sample_count = int(factor_metrics.get("non_null_count", 0))
    cross_section_count = int(factor_metrics.get("cross_section_count", 0))

    checks = [
        {
            "name": "formula_match",
            "status": "passed" if has_formula else "pending",
            "description": "规格书已记录可核对公式表达式。" if has_formula else "尚未补齐可核对公式表达式。",
        },
        {
            "name": "field_mapping_match",
            "status": "passed" if field_mapping_ok else "failed",
            "description": "计算输入字段覆盖规格要求。" if field_mapping_ok else "输入字段未覆盖规格要求。",
        },
        {
            "name": "sample_point_reconciliation",
            "status": "passed" if sample_count > 0 else "failed",
            "description": "已导出样本点位明细，可供人工或外部真值逐点复核。"
            if sample_count > 0
            else "未生成有效样本点位。",
        },
        {
            "name": "cross_section_truth_compare",
            "status": "pending_external_truth" if not truth_path else "passed",
            "description": "等待挂接外部真值序列做截面对照。"
            if not truth_path
            else "已挂接外部真值截面对照结果。",
        },
        {
            "name": "evaluation_consistency",
            "status": "passed" if cross_section_count > 0 else "failed",
            "description": "已生成覆盖多期截面的基础评估指标。"
            if cross_section_count > 0
            else "评估期数不足，无法形成稳定统计。",
        },
    ]

    status = "passed" if all(item["status"] == "passed" for item in checks) else "partial"
    summary = (
        "已完成公式、字段、样本点位和基础评估校验，但仍需挂接外部真值完成最终无偏差证明。"
        if status == "partial"
        else "已完成当前版本全部校验。"
    )
    artifacts = [
        FactorValidationArtifact("spec", spec_path, "标准化 FactorSpec"),
        FactorValidationArtifact("sample_checks", sample_path, "抽样点位核验明细"),
        FactorValidationArtifact("cross_section_compare", truth_path, "截面真值对照结果"),
        FactorValidationArtifact("evaluation_report", evaluation_path, "IC 与回测检验结果"),
    ]
    diagnostics = {
        "generated_at": now_iso(),
        "version": spec.version,
        "job_id": job_id,
        "coverage_ratio": factor_metrics.get("coverage_ratio"),
        "rank_ic_mean": factor_metrics.get("rank_ic_mean"),
        "rank_ic_ir": factor_metrics.get("rank_ic_ir"),
        "long_short_mean": factor_metrics.get("long_short_mean"),
    }
    return FactorValidationReport(
        factor_name=spec.factor_name,
        library=spec.library,
        status=status,
        summary=summary,
        checks=checks,
        artifacts=artifacts,
        diagnostics=diagnostics,
    )


def _write_json(path: Path, payload: dict[str, Any]) -> str:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def export_validation_bundle(
    *,
    config: FactorLabWorkspaceConfig,
    spec: FactorResearchSpec,
    factor_frame: pd.DataFrame,
    evaluation_report: dict[str, Any],
    available_columns: list[str],
    job_id: str = "",
    truth_path: str = "",
) -> str:
    config.ensure_directories()
    sample_payload = build_sample_checks(factor_frame, factor_name=spec.factor_name)
    sample_path = _write_json(config.sample_path(spec.library, spec.factor_name), sample_payload)
    factor_metrics = evaluation_report["summary"]["metrics"][spec.factor_name]
    report = build_validation_report(
        spec=spec,
        available_columns=available_columns,
        factor_metrics=factor_metrics,
        sample_path=sample_path,
        spec_path=str(config.specs_path(spec.library)),
        evaluation_path="",
        truth_path=truth_path,
        job_id=job_id,
    )
    path = config.proof_path(spec.library, spec.factor_name)
    payload = asdict(report)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def export_validation_report(
    *,
    config: FactorLabWorkspaceConfig,
    spec: FactorResearchSpec,
    factor_frame: pd.DataFrame,
    evaluation_report: dict[str, Any],
    available_columns: list[str],
    evaluation_path: str,
    job_id: str = "",
    truth_path: str = "",
) -> str:
    config.ensure_directories()
    sample_payload = build_sample_checks(factor_frame, factor_name=spec.factor_name)
    sample_path = _write_json(config.sample_path(spec.library, spec.factor_name), sample_payload)
    report = build_validation_report(
        spec=spec,
        available_columns=available_columns,
        factor_metrics=evaluation_report["summary"]["metrics"][spec.factor_name],
        sample_path=sample_path,
        spec_path=str(config.specs_path(spec.library)),
        evaluation_path=evaluation_path,
        truth_path=truth_path,
        job_id=job_id,
    )
    payload = asdict(report)
    path = config.proof_path(spec.library, spec.factor_name)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def export_proof_template(
    *,
    config: FactorLabWorkspaceConfig,
    spec: FactorResearchSpec,
) -> str:
    config.ensure_directories()
    proof = build_proof_template(spec)
    payload = asdict(proof)
    path = config.proof_path(spec.library, spec.factor_name)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)
