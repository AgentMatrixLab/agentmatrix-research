from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research_core.factor_lab.truth import compare_factor_to_truth


def _slice_overlap(
    computed: pd.DataFrame,
    truth: pd.DataFrame,
    *,
    start_date: str,
    end_date: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    comp = computed.copy()
    ref = truth.copy()
    comp["date"] = pd.to_datetime(comp["date"])
    ref["date"] = pd.to_datetime(ref["date"])
    comp = comp[(comp["date"] >= start) & (comp["date"] <= end)]
    ref = ref[(ref["date"] >= start) & (ref["date"] <= end)]
    return comp, ref


def build_accuracy_report(
    *,
    computed: pd.DataFrame,
    truth: pd.DataFrame,
    factor_names: list[str],
    overlap_start: str,
    overlap_end: str,
    spearman_threshold: float = 0.95,
    output_dir: str | Path,
) -> dict[str, Any]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    comp, ref = _slice_overlap(computed, truth, start_date=overlap_start, end_date=overlap_end)
    compute_codes = int(comp["code"].nunique())

    common_dates = sorted(set(comp["date"].dt.normalize()).intersection(set(ref["date"].dt.normalize())))
    if common_dates:
        comp = comp[comp["date"].dt.normalize().isin(common_dates)]
        ref = ref[ref["date"].dt.normalize().isin(common_dates)]
    overlap_date_start = str(min(common_dates).date()) if common_dates else overlap_start
    overlap_date_end = str(max(common_dates).date()) if common_dates else overlap_end

    common_codes = sorted(set(comp["code"]).intersection(set(ref["code"])))
    comp = comp[comp["code"].isin(common_codes)]
    ref = ref[ref["code"].isin(common_codes)]

    rows: list[dict[str, Any]] = []
    for factor in factor_names:
        metrics = compare_factor_to_truth(comp, ref, factor_name=factor, tolerance=1e-6)
        spearman = metrics.get("cross_section_spearman_mean", float("nan"))
        truth_non_null = int(ref[factor].notna().sum()) if factor in ref.columns else 0
        if truth_non_null == 0:
            rows.append(
                {
                    "factor": factor,
                    "compared_count": metrics.get("compared_count", 0),
                    "cross_section_spearman_mean": float("nan"),
                    "cross_section_pearson_mean": float("nan"),
                    "max_abs_error": float("nan"),
                    "mean_abs_error": float("nan"),
                    "deviation_rate": float("nan"),
                    "threshold": spearman_threshold,
                    "status": "SKIP",
                    "skip_reason": "qlib truth 无有效值（如本地 cn_data 缺少 $vwap 字段）",
                }
            )
            continue

        deviation = 1.0 - spearman if pd.notna(spearman) else float("nan")
        passed = bool(pd.notna(spearman) and spearman >= spearman_threshold)
        rows.append(
            {
                "factor": factor,
                "compared_count": metrics.get("compared_count", 0),
                "cross_section_spearman_mean": spearman,
                "cross_section_pearson_mean": metrics.get("cross_section_pearson_mean"),
                "max_abs_error": metrics.get("max_abs_error"),
                "mean_abs_error": metrics.get("mean_abs_error"),
                "deviation_rate": deviation,
                "threshold": spearman_threshold,
                "status": "PASS" if passed else "FAIL",
            }
        )

    actionable = [row for row in rows if row["status"] != "SKIP"]
    report = {
        "compute_note": (
            "因子计算使用 SmartData 全市场股票与数据库实际交易日；"
            "仅精度检验时与 qlib truth 取日期/股票交集。"
        ),
        "overlap_start": overlap_start,
        "overlap_end": overlap_end,
        "overlap_date_start": overlap_date_start,
        "overlap_date_end": overlap_date_end,
        "overlap_dates": len(common_dates),
        "compute_codes": compute_codes,
        "common_codes": len(common_codes),
        "factors": rows,
        "passed_count": sum(1 for row in rows if row["status"] == "PASS"),
        "failed_count": sum(1 for row in rows if row["status"] == "FAIL"),
        "skipped_count": sum(1 for row in rows if row["status"] == "SKIP"),
        "overall_status": (
            "PASS"
            if actionable and all(row["status"] == "PASS" for row in actionable)
            else "PARTIAL"
        ),
    }

    json_path = output_dir / "accuracy_report.json"
    md_path = output_dir / "accuracy_report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Alpha158 单因子计算精度报告",
        "",
        f"- 计算股票数（对照窗口内）: {compute_codes}",
        f"- 对照区间（配置）: `{overlap_start}` ~ `{overlap_end}`",
        f"- 对照区间（实际日期交集）: `{overlap_date_start}` ~ `{overlap_date_end}`（{len(common_dates)} 个交易日）",
        f"- 对照来源: qlib Alpha158 Handler",
        f"- 检验股票数（与 qlib 交集）: {len(common_codes)}",
        f"- 通过阈值: 截面 Spearman >= {spearman_threshold}",
        "",
        "| 因子 | Spearman | 偏差率 | 最大绝对误差 | 状态 |",
        "|---|---:|---:|---:|---|",
    ]
    for row in rows:
        if row["status"] == "SKIP":
            reason = row.get("skip_reason", "truth 无有效值")
            lines.append(f"| {row['factor']} | - | - | - | SKIP ({reason}) |")
            continue
        spearman = row["cross_section_spearman_mean"]
        deviation = row["deviation_rate"]
        lines.append(
            f"| {row['factor']} | {spearman:.4f} | {deviation:.2%} | {row['max_abs_error']:.6f} | {row['status']} |"
            if pd.notna(spearman)
            else f"| {row['factor']} | - | - | - | {row['status']} |"
        )
    lines.extend(["", f"**Overall:** {report['overall_status']}"])
    md_path.write_text("\n".join(lines), encoding="utf-8")
    report["json_path"] = str(json_path.resolve())
    report["markdown_path"] = str(md_path.resolve())
    return report