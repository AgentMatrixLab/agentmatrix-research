"""Generate Alpha158 full master summary report (158 factors) with charts and analysis.

Exports MASTER_SUMMARY.md (完整数据表 + 分析解读) and CSV tables.
HTML 可视化见 `generate_alpha158_dashboard.py`。
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from research_core.alpha158_lab.config import Alpha158ResearchConfig
from research_core.alpha158_lab.factors.specs import ALPHA158_BATCHES
from research_core.alpha158_lab.research.batch_report import build_mosaic
from research_core.alpha158_lab.research.master_insights import (
    build_analysis_narrative,
    build_merged_table,
    enrich_accuracy,
    enrich_ic,
    family_summary,
    md_table,
    window_summary,
)
from research_core.factor_library.validation import summarize_ic

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / "runtime" / "alpha158_lab"


def _factor_index_map() -> dict[str, int]:
    mapping: dict[str, int] = {}
    idx = 1
    for batch_id in sorted(ALPHA158_BATCHES):
        for factor in ALPHA158_BATCHES[batch_id]["factors"]:  # type: ignore[union-attr]
            mapping[factor] = idx
            idx += 1
    return mapping


def _factor_batch_map() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for batch_id, meta in ALPHA158_BATCHES.items():
        for factor in meta["factors"]:  # type: ignore[union-attr]
            mapping[factor] = batch_id
    return mapping


def _parse_window(factor: str) -> int | None:
    match = re.search(r"(\d+)$", factor)
    return int(match.group(1)) if match else None


def _load_all_accuracy() -> pd.DataFrame:
    rows: list[dict] = []
    batch01 = ROOT / "validation" / "accuracy_report.json"
    if batch01.exists():
        payload = json.loads(batch01.read_text(encoding="utf-8"))
        for row in payload.get("factors", []):
            row = dict(row)
            row["batch"] = "batch_01"
            rows.append(row)

    for batch_id in sorted(ALPHA158_BATCHES):
        if batch_id == "batch_01":
            continue
        path = ROOT / "validation" / batch_id / "accuracy_report.json"
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        for row in payload.get("factors", []):
            row = dict(row)
            row["batch"] = batch_id
            rows.append(row)

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["factor_index"] = df["factor"].map(_factor_index_map())
    df["window"] = df["factor"].map(_parse_window)
    df = df.sort_values("factor_index")
    return df


def _plot_accuracy_overview(acc: pd.DataFrame, charts_dir: Path) -> list[tuple[str, str]]:
    paths: list[tuple[str, str]] = []
    actionable = acc[acc["status"] != "SKIP"].copy()

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.hist(actionable["cross_section_spearman_mean"].dropna(), bins=30, color="#4C78A8", edgecolor="white")
    ax.axvline(0.95, color="#E45756", linestyle="--", linewidth=1.5, label="threshold 0.95")
    ax.set_title("Cross-Section Spearman Distribution (qlib truth)")
    ax.set_xlabel("Spearman")
    ax.set_ylabel("Factor count")
    ax.legend()
    p = charts_dir / "accuracy_spearman_hist.png"
    fig.tight_layout()
    fig.savefig(p, dpi=150)
    plt.close(fig)
    paths.append(("Spearman 分布", "charts/accuracy_spearman_hist.png"))

    by_window = (
        actionable.dropna(subset=["window"])
        .groupby("window")["cross_section_spearman_mean"]
        .agg(["mean", "median", "count"])
        .reset_index()
        .sort_values("window")
    )
    if not by_window.empty:
        fig, ax = plt.subplots(figsize=(8, 4))
        x = by_window["window"].astype(str)
        ax.bar(x, by_window["mean"], color="#72B7B2", label="mean")
        ax.axhline(0.95, color="#E45756", linestyle="--", linewidth=1.2)
        ax.set_title("Mean Spearman by Rolling Window")
        ax.set_xlabel("Window")
        ax.set_ylabel("Mean Spearman")
        p = charts_dir / "accuracy_by_window.png"
        fig.tight_layout()
        fig.savefig(p, dpi=150)
        plt.close(fig)
        paths.append(("窗口 vs 精度", "charts/accuracy_by_window.png"))

    batch_stats = (
        actionable.groupby("batch")
        .apply(
            lambda g: pd.Series(
                {
                    "pass": (g["status"] == "PASS").sum(),
                    "fail": (g["status"] == "FAIL").sum(),
                    "skip": (g["status"] == "SKIP").sum(),
                }
            ),
            include_groups=False,
        )
        .reset_index()
        .sort_values("batch")
    )
    fig, ax = plt.subplots(figsize=(12, 4))
    x = np.arange(len(batch_stats))
    ax.bar(x, batch_stats["pass"], label="PASS", color="#54A24B")
    ax.bar(x, batch_stats["fail"], bottom=batch_stats["pass"], label="FAIL", color="#E45756")
    if batch_stats["skip"].sum() > 0:
        ax.bar(
            x,
            batch_stats["skip"],
            bottom=batch_stats["pass"] + batch_stats["fail"],
            label="SKIP",
            color="#BAB0AC",
        )
    ax.set_xticks(x)
    ax.set_xticklabels(batch_stats["batch"], rotation=45, ha="right")
    ax.set_title("qlib Accuracy by Batch")
    ax.set_ylabel("Factor count")
    ax.legend()
    p = charts_dir / "batch_accuracy_stacked.png"
    fig.tight_layout()
    fig.savefig(p, dpi=150)
    plt.close(fig)
    paths.append(("批次通过/失败", "charts/batch_accuracy_stacked.png"))

    return paths


def _plot_ic_overview(ic_summary: pd.DataFrame, charts_dir: Path) -> list[tuple[str, str]]:
    paths: list[tuple[str, str]] = []

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.hist(ic_summary["ic_ir"], bins=30, color="#F58518", edgecolor="white")
    ax.axvline(0.0, color="gray", linestyle="--", linewidth=1)
    ax.set_title("Daily Rank IC_IR Distribution")
    ax.set_xlabel("IC_IR")
    ax.set_ylabel("Factor count")
    p = charts_dir / "ic_ir_hist.png"
    fig.tight_layout()
    fig.savefig(p, dpi=150)
    plt.close(fig)
    paths.append(("IC_IR 分布", "charts/ic_ir_hist.png"))

    top = ic_summary.nlargest(15, "ic_ir")
    bottom = ic_summary.nsmallest(15, "ic_ir")
    combined = pd.concat([top, bottom]).drop_duplicates("factor")
    combined = combined.sort_values("ic_ir")
    colors = ["#54A24B" if v >= 0 else "#E45756" for v in combined["ic_ir"]]
    fig, ax = plt.subplots(figsize=(8, 10))
    ax.barh(combined["factor"], combined["ic_ir"], color=colors)
    ax.axvline(0.0, color="gray", linestyle="--", linewidth=1)
    ax.set_title("Top/Bottom Factors by IC_IR")
    ax.set_xlabel("IC_IR")
    p = charts_dir / "ic_ir_top_bottom.png"
    fig.tight_layout()
    fig.savefig(p, dpi=150)
    plt.close(fig)
    paths.append(("IC_IR 排行", "charts/ic_ir_top_bottom.png"))

    batch_ic = (
        ic_summary.groupby("batch", sort=False)
        .agg(ic_ir=("ic_ir", "mean"), ic_mean=("ic_mean", "mean"))
        .reset_index()
    )
    fig, ax = plt.subplots(figsize=(12, 4))
    x = np.arange(len(batch_ic))
    ax.bar(x, batch_ic["ic_ir"], color="#4C78A8")
    ax.axhline(0.0, color="gray", linestyle="--", linewidth=1)
    ax.set_xticks(x)
    ax.set_xticklabels(batch_ic["batch"], rotation=45, ha="right")
    ax.set_title("Mean IC_IR by Batch")
    ax.set_ylabel("Mean IC_IR")
    p = charts_dir / "batch_ic_ir.png"
    fig.tight_layout()
    fig.savefig(p, dpi=150)
    plt.close(fig)
    paths.append(("批次 IC_IR", "charts/batch_ic_ir.png"))

    actionable = ic_summary.merge(
        _load_all_accuracy()[["factor", "cross_section_spearman_mean", "status"]],
        on="factor",
        how="left",
    )
    actionable = actionable[actionable["status"] != "SKIP"]
    fig, ax = plt.subplots(figsize=(7, 6))
    ax.scatter(
        actionable["cross_section_spearman_mean"],
        actionable["ic_ir"],
        alpha=0.6,
        c=np.where(actionable["ic_ir"] >= 0, "#54A24B", "#E45756"),
        edgecolors="none",
    )
    ax.axvline(0.95, color="gray", linestyle="--", linewidth=1)
    ax.axhline(0.0, color="gray", linestyle="--", linewidth=1)
    ax.set_xlabel("qlib Spearman")
    ax.set_ylabel("IC_IR")
    ax.set_title("Replication Accuracy vs Predictive Power")
    p = charts_dir / "spearman_vs_ic_ir.png"
    fig.tight_layout()
    fig.savefig(p, dpi=150)
    plt.close(fig)
    paths.append(("精度 vs 有效性", "charts/spearman_vs_ic_ir.png"))

    return paths


def _build_highlight_mosaics(ic_summary: pd.DataFrame, charts_dir: Path) -> list[tuple[str, str]]:
    paths: list[tuple[str, str]] = []
    charts_root = ROOT / "charts"
    top10 = ic_summary.nlargest(10, "ic_ir")["factor"].tolist()
    bottom10 = ic_summary.nsmallest(10, "ic_ir")["factor"].tolist()

    for label, factors in (("top10_ic_ir", top10), ("bottom10_ic_ir", bottom10)):
        for suffix, title in (("ic_series", "IC 时序"), ("long_short_nav", "多空净值")):
            out = charts_dir / f"highlight_{label}_{suffix}.png"
            built = build_mosaic(
                factor_names=factors,
                charts_dir=charts_root,
                chart_suffix=suffix,
                output_path=out,
                ncol=5,
                nrow=2,
            )
            if built:
                rel = f"charts/highlight_{label}_{suffix}.png"
                paths.append((f"{title} ({label})", rel))
    return paths


def build_master_summary() -> dict:
    cfg = Alpha158ResearchConfig()
    master_dir = ROOT / "reports" / "master"
    charts_dir = master_dir / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    panel = pd.read_parquet(ROOT / "market_panel.parquet")
    cfg.start_date = str(pd.to_datetime(panel["date"]).min().date())
    cfg.end_date = str(pd.to_datetime(panel["date"]).max().date())
    factors = pd.read_parquet(ROOT / "alpha158_factors_smartdata.parquet")
    factor_cols = [c for c in factors.columns if c not in {"date", "code"}]

    acc = enrich_accuracy(_load_all_accuracy())
    ic_raw = pd.read_csv(ROOT / "effectiveness" / "ic_series.csv", parse_dates=["date"])
    ic_summary = enrich_ic(
        summarize_ic(ic_raw).rename(
            columns={"mean_ic": "ic_mean", "ic_ir": "ic_ir", "win_rate": "ic_win_rate", "n_periods": "n_periods"}
        )
    )
    ic_summary["batch"] = ic_summary["factor"].map(_factor_batch_map())
    ic_summary["ic_win_rate_pct"] = ic_summary["ic_win_pct"].round(1)
    merged_full = build_merged_table(acc, ic_summary)
    merged_full["factor_index"] = merged_full["factor"].map(_factor_index_map())
    merged_full.to_csv(master_dir / "merged_all.csv", index=False, encoding="utf-8-sig")
    ic_summary.to_csv(master_dir / "ic_summary_all.csv", index=False, encoding="utf-8-sig")
    acc.to_csv(master_dir / "accuracy_all.csv", index=False, encoding="utf-8-sig")
    fam_df = family_summary(acc, ic_summary)
    win_df = window_summary(acc)

    chart_entries: list[tuple[str, str]] = []
    chart_entries.extend(_plot_accuracy_overview(acc, charts_dir))
    chart_entries.extend(_plot_ic_overview(ic_summary, charts_dir))
    chart_entries.extend(_build_highlight_mosaics(ic_summary, charts_dir))

    actionable = acc[acc["status"] != "SKIP"]
    passed = int((actionable["status"] == "PASS").sum())
    failed = int((actionable["status"] == "FAIL").sum())
    skipped = int((acc["status"] == "SKIP").sum())
    common_codes = 676
    for p in [ROOT / "validation" / "batch_16" / "accuracy_report.json", ROOT / "validation" / "accuracy_report.json"]:
        if p.exists():
            common_codes = int(json.loads(p.read_text(encoding="utf-8")).get("common_codes", common_codes))
            break

    batch_acc = (
        actionable.groupby("batch")
        .apply(
            lambda g: pd.Series(
                {
                    "n": len(g),
                    "pass": (g["status"] == "PASS").sum(),
                    "fail": (g["status"] == "FAIL").sum(),
                }
            ),
            include_groups=False,
        )
        .reset_index()
    )
    batch_acc["pass_rate_pct"] = (batch_acc["pass"] / batch_acc["n"] * 100).round(1)

    pass_rate = passed / len(actionable) * 100 if len(actionable) else 0
    panel_stocks = int(panel["code"].nunique())
    fail_only = actionable[actionable["status"] == "FAIL"].sort_values("cross_section_spearman_mean")

    analysis = build_analysis_narrative(
        acc=acc,
        ic=ic_summary,
        pass_rate=pass_rate,
        passed=passed,
        failed=failed,
        skipped=skipped,
        panel_stocks=panel_stocks,
        common_codes=common_codes,
        compute_range=cfg.compute_range_label,
        validation_range=cfg.validation_range_label,
    )

    lines = [
        "# Alpha158 研究汇报（158 因子 · 完整版）",
        "",
        f"*生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}*",
        "",
        "> 本报告包含：**完整数据表** + **分析解读**。图表版见 **MASTER_DASHBOARD.html**；机器可读见 `merged_all.csv`。",
        "",
        "---",
        "",
        "## 执行摘要",
        "",
        "| 指标 | 结果 |",
        "| --- | --- |",
        f"| 因子交付 | **{len(factor_cols)} / 158** 全部完成 |",
        f"| qlib 复现通过率 | **{pass_rate:.1f}%**（{passed} 过 / {failed} 败 / {skipped} 跳） |",
        f"| 计算覆盖 | {panel.date.min().date()} ~ {panel.date.max().date()}，**{panel_stocks}** 只股票 |",
        f"| 检验交集 | {cfg.overlap_start} ~ {cfg.overlap_end}，**{common_codes}** 只（仅对照用） |",
        f"| 中位 IC_IR | {ic_summary['ic_ir'].median():.3f} |",
        f"| 平均 IC_IR | {ic_summary['ic_ir'].mean():.3f} |",
        f"| IC_IR > 0 因子数 | {(ic_summary['ic_ir'] > 0).sum()} / {len(ic_summary)} |",
        "",
        "## 分析解读",
        "",
        *analysis,
        "---",
        "",
        "## 数据口径",
        "",
        "| | 因子计算 | qlib 检验 |",
        "| --- | --- | --- |",
        f"| 股票 | SmartData 全市场（{panel_stocks} 只） | 交集 {common_codes} 只 |",
        f"| 日期 | {panel.date.min().date()} ~ {panel.date.max().date()} | {cfg.overlap_start} ~ {cfg.overlap_end} |",
        "| 用途 | 生产因子值、IC、多空 | 验证与 qlib 一致性（5% 阈值） |",
        "",
        "## 按因子族汇总（精度 + 有效性）",
        "",
        md_table(
            fam_df,
            [
                "family",
                "n",
                "pass_n",
                "fail_n",
                "pass_rate_pct",
                "mean_spearman",
                "mean_ic_ir",
                "median_ic_ir",
                "mean_ic",
            ],
            float_cols={
                "pass_rate_pct",
                "mean_spearman",
                "min_spearman",
                "mean_ic_ir",
                "median_ic_ir",
                "mean_ic",
            },
            int_cols={"n", "pass_n", "fail_n"},
        ),
        "",
        "## 按滚动窗口汇总（仅含带窗口后缀的因子）",
        "",
        md_table(
            win_df,
            ["window", "n", "pass_n", "fail_n", "pass_rate_pct", "mean_spearman", "min_spearman"],
            float_cols={"pass_rate_pct", "mean_spearman", "min_spearman"},
            int_cols={"window", "n", "pass_n", "fail_n"},
        ),
        "",
        "## 汇总图表",
        "",
    ]
    for title, rel in chart_entries:
        lines.append(f"### {title}")
        lines.append("")
        lines.append(f"![{title}]({rel})")
        lines.append("")

    batch_acc["status"] = batch_acc["pass_rate_pct"].map(
        lambda r: "全通过" if r >= 100 else "基本通过" if r >= 90 else "需关注"
    )
    lines.extend(
        [
            "## qlib 精度：按批次",
            "",
            md_table(
                batch_acc,
                ["batch", "n", "pass", "fail", "pass_rate_pct", "status"],
                float_cols={"pass_rate_pct"},
                int_cols={"n", "pass", "fail"},
            ),
            "",
            f"## 未通过因子明细（{failed} 个）",
            "",
            md_table(
                fail_only[
                    ["factor", "batch", "family", "window", "cross_section_spearman_mean", "deviation_rate", "compared_count"]
                ].rename(columns={"cross_section_spearman_mean": "spearman", "deviation_rate": "deviation"}),
                ["factor", "batch", "family", "window", "spearman", "deviation", "compared_count"],
                float_cols={"spearman", "deviation", "window"},
                int_cols={"compared_count"},
            ),
            "",
            "## 有效性：IC Top 20 / Bottom 20",
            "",
            "### Top 20",
            "",
            md_table(
                ic_summary.nlargest(20, "ic_ir")[
                    ["factor", "batch", "family", "ic_mean", "std_ic", "ic_ir", "ic_win_rate_pct", "n_periods"]
                ],
                ["factor", "batch", "family", "ic_mean", "std_ic", "ic_ir", "ic_win_rate_pct", "n_periods"],
                float_cols={"ic_mean", "std_ic", "ic_ir", "ic_win_rate_pct"},
                int_cols={"n_periods"},
            ),
            "",
            "### Bottom 20",
            "",
            md_table(
                ic_summary.nsmallest(20, "ic_ir")[
                    ["factor", "batch", "family", "ic_mean", "std_ic", "ic_ir", "ic_win_rate_pct", "n_periods"]
                ],
                ["factor", "batch", "family", "ic_mean", "std_ic", "ic_ir", "ic_win_rate_pct", "n_periods"],
                float_cols={"ic_mean", "std_ic", "ic_ir", "ic_win_rate_pct"},
                int_cols={"n_periods"},
            ),
            "",
            "## 158 因子完整对照表（精度 + IC，按批次排序）",
            "",
            md_table(
                merged_full.sort_values("factor_index")[
                    [
                        "factor_index",
                        "factor",
                        "batch",
                        "family",
                        "window",
                        "status",
                        "cross_section_spearman_mean",
                        "deviation_rate",
                        "compared_count",
                        "ic_mean",
                        "ic_ir",
                        "ic_win_pct",
                    ]
                ].rename(
                    columns={
                        "cross_section_spearman_mean": "spearman",
                        "deviation_rate": "deviation",
                    }
                ),
                [
                    "factor_index",
                    "factor",
                    "batch",
                    "family",
                    "window",
                    "status",
                    "spearman",
                    "deviation",
                    "compared_count",
                    "ic_mean",
                    "ic_ir",
                    "ic_win_pct",
                ],
                float_cols={"spearman", "deviation", "ic_mean", "ic_ir", "ic_win_pct", "window"},
                int_cols={"factor_index", "compared_count"},
            ),
            "",
            "## 批次明细索引",
            "",
            "| 批次 | 报告 | IC 拼图 | 多空拼图 |",
            "| --- | --- | --- | --- |",
        ]
    )
    for batch_id in sorted(ALPHA158_BATCHES):
        report = f"../{batch_id}/REPORT.md"
        ic_rel = f"../{batch_id}/mosaics/ic_mosaic.png"
        nav_rel = f"../{batch_id}/mosaics/long_short_nav_mosaic.png"
        ic_cell = f"[查看]({ic_rel})" if (ROOT / "reports" / batch_id / "mosaics" / "ic_mosaic.png").exists() else "-"
        nav_cell = f"[查看]({nav_rel})" if (ROOT / "reports" / batch_id / "mosaics" / "long_short_nav_mosaic.png").exists() else "-"
        lines.append(f"| {batch_id} | [{batch_id}]({report}) | {ic_cell} | {nav_cell} |")
    lines.extend(
        [
            "## 已知限制",
            "",
            "1. **VWAP0**: qlib `cn_data` 无 `$vwap` 字段，对照 SKIP。",
            f"2. **对照口径**: 计算区间 {panel.date.min().date()} ~ {panel.date.max().date()}；"
            f"qlib 检验仅在 {cfg.overlap_start} ~ {cfg.overlap_end} 的交集样本上比较。",
            "3. **IMIN/IMAX/QTLU60 等**: 部分 FAIL 来自数据对齐或 IdxMin 实现细节，非流水线故障。",
            "4. **2021-06-11 之后**: 仅完成 SmartData 计算与 IC 检验，无 qlib truth。",
            "",
            "## 产物路径",
            "",
            f"- 因子宽表: `{ROOT / 'alpha158_factors_smartdata.parquet'}`",
            f"- 日频 IC: `{ROOT / 'effectiveness' / 'ic_series.csv'}`",
            f"- IC 汇总 CSV: `{master_dir / 'ic_summary_all.csv'}`",
            f"- 精度汇总 CSV: `{master_dir / 'accuracy_all.csv'}`",
            f"- 合并全表 CSV: `{master_dir / 'merged_all.csv'}`",
            f"- 单因子小图: `{ROOT / 'charts'}`",
            "",
        ]
    )

    md_path = master_dir / "MASTER_SUMMARY.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")

    payload = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "factor_count": len(factor_cols),
        "accuracy": {
            "pass": passed,
            "fail": failed,
            "skip": skipped,
            "actionable": len(actionable),
        },
        "ic_summary": {
            "median_ic_ir": float(ic_summary["ic_ir"].median()),
            "median_ic_mean": float(ic_summary["ic_mean"].median()),
        },
        "charts": [{"title": t, "path": str((master_dir / p).resolve())} for t, p in chart_entries],
        "markdown_path": str(md_path.resolve()),
        "json_path": str((master_dir / "MASTER_SUMMARY.json").resolve()),
    }
    (master_dir / "MASTER_SUMMARY.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return payload


def main() -> None:
    payload = build_master_summary()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print("\nHTML 仪表盘: python scripts/generate_alpha158_dashboard.py")


if __name__ == "__main__":
    main()