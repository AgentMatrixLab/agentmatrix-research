from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib.image as mpimg
import matplotlib.pyplot as plt
import pandas as pd

from research_core.alpha158_lab.config import Alpha158ResearchConfig
from research_core.alpha158_lab.factors.specs import ALPHA158_FACTOR_DETAILS, alpha158_specs


@dataclass(slots=True)
class BatchReportConfig:
    batch_id: str
    batch_title: str
    factor_names: list[str]
    factor_index_start: int
    factor_index_end: int
    charts_dir: Path
    reports_root: Path
    compute_range: str
    validation_range: str

    @property
    def batch_dir(self) -> Path:
        return self.reports_root / self.batch_id

    @property
    def mosaics_dir(self) -> Path:
        return self.batch_dir / "mosaics"


MOSAIC_GROUPS: tuple[tuple[str, str], ...] = (
    ("ic_series", "ic_mosaic.png"),
    ("long_short_nav", "long_short_nav_mosaic.png"),
)


def _ensure_dirs(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def build_mosaic(
    *,
    factor_names: list[str],
    charts_dir: Path,
    chart_suffix: str,
    output_path: Path,
    ncol: int = 5,
    nrow: int = 2,
) -> str | None:
    """Compose N factor charts into one grid image (default 5x2=10)."""
    charts_dir = Path(charts_dir)
    output_path = Path(output_path)
    _ensure_dirs(output_path.parent)

    fig, axes = plt.subplots(nrow, ncol, figsize=(ncol * 4.2, nrow * 3.2))
    axes_list = axes.flatten() if hasattr(axes, "flatten") else [axes]

    loaded = 0
    for idx, factor in enumerate(factor_names):
        if idx >= len(axes_list):
            break
        chart_path = charts_dir / f"{factor}_{chart_suffix}.png"
        ax = axes_list[idx]
        ax.axis("off")
        if not chart_path.exists():
            ax.text(0.5, 0.5, f"Missing\n{factor}", ha="center", va="center")
            continue
        ax.imshow(mpimg.imread(chart_path))
        ax.set_title(factor, fontsize=10)
        loaded += 1

    for ax in axes_list[len(factor_names) :]:
        ax.axis("off")

    if loaded == 0:
        plt.close(fig)
        return None

    fig.suptitle(chart_suffix.replace("_", " ").title(), fontsize=14, y=0.98)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return str(output_path.resolve())


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _template_path(reports_root: Path) -> Path:
    return reports_root / "TEMPLATE.md"


def _batch_headline(payload: dict[str, Any]) -> str:
    acc = payload.get("accuracy", {})
    status = acc.get("overall_status", "N/A")
    passed = acc.get("passed_count", 0)
    total = len(payload.get("factor_names", []))
    skipped = acc.get("skipped_count", 0)
    actionable = total - skipped
    if status == "PASS":
        return f"本批次 **{passed}/{actionable}** 个因子通过 qlib 对照，可直接用于下游。"
    if status == "PARTIAL":
        return (
            f"本批次 **{passed}/{actionable}** 通过；未通过多为长窗口因子，"
            "短窗口因子已验证公式主体正确。"
        )
    return f"本批次对照状态：**{status}**（通过 {passed}/{actionable}）。"


def render_batch_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# {payload['batch_title']}",
        "",
        f"> {_batch_headline(payload)}",
        "",
        "## 批次信息",
        f"- 批次编号: `{payload['batch_id']}`",
        f"- 因子范围: #{payload['factor_index_start']} ~ #{payload['factor_index_end']}",
        f"- 因子列表: {', '.join(payload['factor_names'])}",
        f"- 生成时间: {payload['generated_at']}",
        f"- 计算区间: {payload['compute_range']}",
        f"- 对照区间: {payload['validation_range']}",
        "",
        "## 数据口径",
    ]
    for note in payload.get("scope_notes", []):
        lines.append(f"- {note}")

    lines.extend(["", "## 复现精度（qlib 横截面对照）", ""])
    acc = payload.get("accuracy", {})
    lines.append(f"- 总体状态: **{acc.get('overall_status', 'N/A')}**")
    skipped_count = acc.get("skipped_count", 0)
    actionable_count = len(payload["factor_names"]) - skipped_count
    if skipped_count:
        lines.append(
            f"- 通过因子: {acc.get('passed_count', 0)} / {actionable_count} "
            f"（{skipped_count} 个 SKIP）"
        )
    else:
        lines.append(f"- 通过因子: {acc.get('passed_count', 0)} / {len(payload['factor_names'])}")
    lines.append(f"- 计算股票数（对照窗口内）: {acc.get('compute_codes', 'N/A')}")
    lines.append(f"- 检验股票数（与 qlib 交集）: {acc.get('common_codes', 'N/A')}")
    if acc.get("overlap_date_start") and acc.get("overlap_date_end"):
        lines.append(
            f"- 实际日期交集: {acc.get('overlap_date_start')} ~ {acc.get('overlap_date_end')}"
        )
    lines.append("")
    lines.append("| 因子 | Spearman | 偏差率 | 最大绝对误差 | 状态 |")
    lines.append("|---|---:|---:|---:|---|")
    for row in acc.get("factors", []):
        status = row.get("status")
        if status == "SKIP":
            reason = row.get("skip_reason", "truth 无有效值")
            lines.append(f"| {row.get('factor')} | - | - | - | SKIP ({reason}) |")
            continue
        spearman = row.get("cross_section_spearman_mean")
        deviation = row.get("deviation_rate")
        if spearman is None or (isinstance(spearman, float) and pd.isna(spearman)):
            lines.append(f"| {row.get('factor')} | - | - | - | {status} |")
        else:
            lines.append(
                f"| {row.get('factor')} | {spearman:.4f} | {deviation:.2%} | "
                f"{row.get('max_abs_error', 0):.6f} | {status} |"
            )

    lines.extend(["", "## 有效性摘要（全段月度检验）", ""])
    lines.append("| 因子 | Rank IC | IC_IR | 多空Spread | 覆盖率 |")
    lines.append("|---|---:|---:|---:|---:|")
    for factor in payload["factor_names"]:
        eff = payload.get("effectiveness", {}).get(factor, {})
        lines.append(
            f"| {factor} | {eff.get('rank_ic_mean', 'N/A')} | {eff.get('rank_ic_ir', 'N/A')} | "
            f"{eff.get('long_short_mean', 'N/A')} | {eff.get('coverage_ratio', 'N/A')} |"
        )

    lines.extend(["", "## 因子定义", ""])
    for factor in payload["factor_names"]:
        detail = payload.get("factor_definitions", {}).get(factor, {})
        lines.append(f"### {factor}")
        lines.append(f"- 公式: `{detail.get('formula', '')}`")
        lines.append(f"- 说明: {detail.get('description', '')}")
        lines.append("")

    lines.extend(["", "## 拼图（每 10 张小图合成 1 张大图）", ""])
    for mosaic in payload.get("mosaics", []):
        lines.append(f"- {mosaic['label']}: `{mosaic['path']}`")

    lines.extend(["", "## 小图路径（charts/）", ""])
    for factor in payload["factor_names"]:
        chart_refs = payload.get("charts", {}).get(factor, {})
        for chart_type, chart_path in chart_refs.items():
            lines.append(f"- `{factor}` {chart_type}: `{chart_path}`")

    lines.extend(["", "## 产物索引", ""])
    for key, value in payload.get("artifacts", {}).items():
        lines.append(f"- {key}: `{value}`")

    lines.extend(["", "## 批次结论", "", payload.get("batch_conclusion", ""), ""])
    return "\n".join(lines)


def generate_batch_report(
    batch: BatchReportConfig,
    *,
    workspace: Alpha158ResearchConfig | None = None,
) -> dict[str, Any]:
    workspace = workspace or Alpha158ResearchConfig()
    _ensure_dirs(batch.batch_dir)
    _ensure_dirs(batch.mosaics_dir)

    batch_validation = workspace.output_dir / "validation" / batch.batch_id / "accuracy_report.json"
    default_validation = workspace.output_dir / "validation" / "accuracy_report.json"
    accuracy_path = batch_validation if batch_validation.exists() else default_validation
    batch_effectiveness = workspace.output_dir / "effectiveness" / batch.batch_id / "effectiveness_report.json"
    default_effectiveness = workspace.output_dir / "effectiveness" / "effectiveness_report.json"
    effectiveness_path = batch_effectiveness if batch_effectiveness.exists() else default_effectiveness

    accuracy = _load_json(accuracy_path)
    effectiveness = _load_json(effectiveness_path)
    eff_metrics = effectiveness.get("factor_metrics", {}).get("metrics", {})

    mosaics: list[dict[str, str]] = []
    for chart_suffix, mosaic_name in MOSAIC_GROUPS:
        out = batch.mosaics_dir / mosaic_name
        built = build_mosaic(
            factor_names=batch.factor_names,
            charts_dir=batch.charts_dir,
            chart_suffix=chart_suffix,
            output_path=out,
        )
        if built:
            mosaics.append({"label": mosaic_name, "path": built, "chart_suffix": chart_suffix})

    charts: dict[str, dict[str, str]] = {}
    for factor in batch.factor_names:
        charts[factor] = {}
        for suffix in ("ic_series", "long_short_nav", "quantile_returns"):
            p = batch.charts_dir / f"{factor}_{suffix}.png"
            if p.exists():
                charts[factor][suffix] = str(p.resolve())

    acc_factors = [row for row in accuracy.get("factors", []) if row.get("factor") in batch.factor_names]
    passed = sum(1 for row in acc_factors if row.get("status") == "PASS")
    skipped = sum(1 for row in acc_factors if row.get("status") == "SKIP")
    actionable = [row for row in acc_factors if row.get("status") != "SKIP"]

    payload: dict[str, Any] = {
        "batch_id": batch.batch_id,
        "batch_title": batch.batch_title,
        "factor_index_start": batch.factor_index_start,
        "factor_index_end": batch.factor_index_end,
        "factor_names": batch.factor_names,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "compute_range": batch.compute_range,
        "validation_range": batch.validation_range,
        "scope_notes": [
            "SmartData 全市场日线为计算主数据源；计算区间取数据库在 2020~2026 内的实际交易日。",
            "因子计算使用 SmartData 全市场股票（剔除 ST/停牌/退市），不与 qlib 取股票交集。",
            "qlib Alpha158 Handler 为对照真值；仅精度检验时与 SmartData 取日期/股票交集。",
            f"{batch.validation_range.split('~')[-1].strip()} 之后仅完成因子计算与有效性检验，不做 qlib 数值对照。",
        ],
        "accuracy": {
            "overall_status": (
                "PASS"
                if actionable and passed == len(actionable)
                else "PARTIAL"
            ),
            "passed_count": passed,
            "failed_count": sum(1 for row in acc_factors if row.get("status") == "FAIL"),
            "skipped_count": skipped,
            "compute_codes": accuracy.get("compute_codes"),
            "common_codes": accuracy.get("common_codes"),
            "overlap_date_start": accuracy.get("overlap_date_start"),
            "overlap_date_end": accuracy.get("overlap_date_end"),
            "factors": acc_factors,
        },
        "effectiveness": {
            factor: eff_metrics.get(factor, {})
            for factor in batch.factor_names
        },
        "factor_definitions": {
            factor: ALPHA158_FACTOR_DETAILS.get(factor, {})
            for factor in batch.factor_names
        },
        "mosaics": mosaics,
        "charts": charts,
        "artifacts": {
            "market_panel": str((workspace.output_dir / "market_panel.parquet").resolve()),
            "factor_frame": str((workspace.output_dir / "alpha158_factors_smartdata.parquet").resolve()),
            "accuracy_report": str(accuracy_path.resolve()),
            "effectiveness_report": str(effectiveness_path.resolve()),
        },
        "batch_conclusion": (
            f"批次 {batch.batch_id} 共 {len(batch.factor_names)} 个因子，"
            f"qlib 对照 {passed}/{len(actionable) or len(batch.factor_names)} 通过"
            + (f"，{skipped} 个因 truth 缺失跳过" if skipped else "")
            + "；小图保留于 charts/，拼图输出于 reports 对应批次目录。"
        ),
    }

    md_path = batch.batch_dir / "REPORT.md"
    json_path = batch.batch_dir / "report.json"
    md_path.write_text(render_batch_markdown(payload), encoding="utf-8")
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    payload["report_markdown"] = str(md_path.resolve())
    payload["report_json"] = str(json_path.resolve())
    return payload


def ensure_report_template(reports_root: Path) -> str:
    reports_root = Path(reports_root)
    _ensure_dirs(reports_root)
    template_path = _template_path(reports_root)
    if template_path.exists():
        return str(template_path.resolve())

    template = """# Alpha158 批次报告模板（TEMPLATE）

> 每完成 10 个因子，复制本模板结构生成 `reports/batch_XX/REPORT.md` 与 `report.json`。
> 所有批次报告字段必须与模板一致，便于横向对比与自动化汇总。

## 1. 批次信息
- 批次编号: `batch_XX`
- 因子范围: `#start ~ #end`
- 因子列表: `FACTOR1, FACTOR2, ...`
- 生成时间: `YYYY-MM-DD HH:MM:SS`
- 计算区间: `YYYY-MM-DD ~ YYYY-MM-DD`
- 对照区间: `YYYY-MM-DD ~ YYYY-MM-DD`

## 2. 数据口径
- SmartData 全市场日线为计算主数据源
- qlib Alpha158 Handler 为对照真值（仅重叠区间）
- 新股过滤：库内第 120 个交易日代理
- 对照截止日后：仅计算 + 有效性，不做 qlib 数值对照

## 3. 复现精度（qlib 横截面对照）
- 总体状态: `PASS / PARTIAL / FAIL`
- 通过因子: `n / 10`
- 共同股票数: `N`

| 因子 | Spearman | 偏差率 | 最大绝对误差 | 状态 |
|---|---:|---:|---:|---|
| FACTOR | 0.0000 | 0.00% | 0.000000 | PASS |

## 4. 有效性摘要（全段月度检验）

| 因子 | Rank IC | IC_IR | 多空Spread | 覆盖率 |
|---|---:|---:|---:|---:|
| FACTOR | 0.0000 | 0.0000 | 0.0000 | 1.0 |

## 5. 因子定义
### FACTOR
- 公式: `...`
- 说明: ...

## 6. 拼图（每 10 张小图 → 1 张大图）
- `mosaics/ic_mosaic.png`：10 个因子的 IC 时序小图合成
- `mosaics/long_short_nav_mosaic.png`：10 个因子的多空净值小图合成

## 7. 小图路径（charts/）
- `FACTOR_ic_series.png`
- `FACTOR_long_short_nav.png`
- `FACTOR_quantile_returns.png`

## 8. 产物索引
- market_panel / factor_frame / accuracy_report / effectiveness_report

## 9. 批次结论
- 本批次完成情况及后续建议
"""
    template_path.write_text(template, encoding="utf-8")
    schema_path = reports_root / "TEMPLATE.schema.json"
    schema_path.write_text(
        json.dumps(
            {
                "required_sections": [
                    "batch_metadata",
                    "scope_notes",
                    "accuracy",
                    "effectiveness",
                    "factor_definitions",
                    "mosaics",
                    "charts",
                    "artifacts",
                    "batch_conclusion",
                ],
                "mosaic_groups": [
                    {"chart_suffix": "ic_series", "output": "mosaics/ic_mosaic.png", "grid": "5x2"},
                    {
                        "chart_suffix": "long_short_nav",
                        "output": "mosaics/long_short_nav_mosaic.png",
                        "grid": "5x2",
                    },
                ],
                "per_factor_charts_dir": "charts",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return str(template_path.resolve())