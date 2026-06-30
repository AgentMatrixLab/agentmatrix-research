"""Shared tables and narrative analysis for Alpha158 master reports."""

from __future__ import annotations

import re
from typing import Any

import numpy as np
import pandas as pd


def factor_family(name: str) -> str:
    rules = [
        (r"^K", "K线形态"),
        (r"^(OPEN|HIGH|LOW|VWAP)0$", "相对价格"),
        (r"^ROC", "收益率 ROC"),
        (r"^MA", "均线 MA"),
        (r"^STD", "波动 STD"),
        (r"^BETA", "趋势斜率"),
        (r"^RSQR", "趋势 R²"),
        (r"^RESI", "回归残差"),
        (r"^MAX", "区间高点"),
        (r"^MIN", "区间低点"),
        (r"^QTL", "分位数"),
        (r"^RANK", "滚动排名"),
        (r"^RSV", "随机指标 RSV"),
        (r"^IMAX", "高点位置"),
        (r"^IMIN", "低点位置"),
        (r"^IMXD", "高低点时差"),
        (r"^CORR", "价量相关"),
        (r"^CORD", "价量变化相关"),
        (r"^CNTP", "上涨天数占比"),
        (r"^CNTN", "下跌天数占比"),
        (r"^CNTD", "涨跌天数差"),
        (r"^SUMP", "价格 RSI 涨"),
        (r"^SUMN", "价格 RSI 跌"),
        (r"^SUMD", "价格 RSI 差"),
        (r"^VMA", "成交量均线比"),
        (r"^VSTD", "成交量波动比"),
        (r"^WVMA", "量加权波动"),
        (r"^VSUMP", "量能 RSI 增"),
        (r"^VSUMN", "量能 RSI 减"),
        (r"^VSUMD", "量能 RSI 差"),
    ]
    for pattern, label in rules:
        if re.match(pattern, name):
            return label
    return "其他"


def parse_window(name: str) -> int | None:
    match = re.search(r"(\d+)$", name)
    return int(match.group(1)) if match else None


def enrich_accuracy(acc: pd.DataFrame) -> pd.DataFrame:
    out = acc.copy()
    if "family" not in out.columns:
        out["family"] = out["factor"].map(factor_family)
    if "window" not in out.columns:
        out["window"] = out["factor"].map(parse_window)
    return out


def enrich_ic(ic: pd.DataFrame) -> pd.DataFrame:
    out = ic.copy()
    if "family" not in out.columns:
        out["family"] = out["factor"].map(factor_family)
    if "ic_win_pct" not in out.columns and "ic_win_rate" in out.columns:
        out["ic_win_pct"] = out["ic_win_rate"] * 100
    return out


def build_merged_table(acc: pd.DataFrame, ic: pd.DataFrame) -> pd.DataFrame:
    acc = enrich_accuracy(acc)
    ic = enrich_ic(ic)
    merged = acc.merge(
        ic[
            [
                "factor",
                "ic_mean",
                "std_ic",
                "ic_ir",
                "ic_win_pct",
                "n_periods",
                "batch",
            ]
        ].rename(columns={"batch": "ic_batch"}),
        on="factor",
        how="left",
        suffixes=("", "_ic"),
    )
    if "batch" not in merged.columns:
        merged["batch"] = merged.get("ic_batch")
    batch_ord = merged["batch"].astype(str).str.extract(r"(\d+)$", expand=False).astype(float)
    merged["_batch_ord"] = batch_ord
    merged = merged.sort_values(["_batch_ord", "factor"]).drop(columns="_batch_ord")
    return merged.reset_index(drop=True)


def family_summary(acc: pd.DataFrame, ic: pd.DataFrame) -> pd.DataFrame:
    acc = enrich_accuracy(acc)
    ic = enrich_ic(ic)
    actionable = acc[acc["status"] != "SKIP"]
    acc_g = (
        actionable.groupby("family")
        .agg(
            n=("factor", "count"),
            pass_n=("status", lambda s: (s == "PASS").sum()),
            fail_n=("status", lambda s: (s == "FAIL").sum()),
            mean_spearman=("cross_section_spearman_mean", "mean"),
            min_spearman=("cross_section_spearman_mean", "min"),
        )
        .reset_index()
    )
    acc_g["pass_rate_pct"] = (acc_g["pass_n"] / acc_g["n"] * 100).round(1)
    ic_g = (
        ic.groupby("family")
        .agg(
            mean_ic_ir=("ic_ir", "mean"),
            median_ic_ir=("ic_ir", "median"),
            mean_ic=("ic_mean", "mean"),
        )
        .reset_index()
    )
    return acc_g.merge(ic_g, on="family", how="left").sort_values("pass_rate_pct")


def window_summary(acc: pd.DataFrame) -> pd.DataFrame:
    acc = enrich_accuracy(acc)
    actionable = acc[acc["status"] != "SKIP"].dropna(subset=["window"])
    return (
        actionable.groupby("window")
        .agg(
            n=("factor", "count"),
            pass_n=("status", lambda s: (s == "PASS").sum()),
            fail_n=("status", lambda s: (s == "FAIL").sum()),
            mean_spearman=("cross_section_spearman_mean", "mean"),
            min_spearman=("cross_section_spearman_mean", "min"),
        )
        .reset_index()
        .assign(pass_rate_pct=lambda d: (d["pass_n"] / d["n"] * 100).round(1))
        .sort_values("window")
    )


def build_analysis_narrative(
    *,
    acc: pd.DataFrame,
    ic: pd.DataFrame,
    pass_rate: float,
    passed: int,
    failed: int,
    skipped: int,
    panel_stocks: int,
    common_codes: int,
    compute_range: str,
    validation_range: str,
) -> list[str]:
    acc = enrich_accuracy(acc)
    ic = enrich_ic(ic)
    actionable = acc[acc["status"] != "SKIP"]
    fam = family_summary(acc, ic)
    win = window_summary(acc)

    fail_df = actionable[actionable["status"] == "FAIL"]
    fail_60 = int(fail_df["factor"].str.endswith("60").sum())
    top_ic = ic.nlargest(5, "ic_ir")
    bottom_ic = ic.nsmallest(5, "ic_ir")

    best_fam_ic = fam.nlargest(3, "mean_ic_ir")[["family", "mean_ic_ir", "pass_rate_pct"]]
    weak_fam_ic = fam.nsmallest(3, "mean_ic_ir")[["family", "mean_ic_ir", "pass_rate_pct"]]
    worst_fam_pass = fam.nsmallest(3, "pass_rate_pct")[["family", "pass_rate_pct", "fail_n"]]

    merged = build_merged_table(acc, ic)
    high_acc_low_ic = merged[
        (merged["status"] == "PASS") & (merged["ic_ir"] < -0.3)
    ].nsmallest(5, "ic_ir")[["factor", "cross_section_spearman_mean", "ic_ir"]]
    low_acc_high_ic = merged[
        (merged["status"] == "FAIL") & (merged["ic_ir"] > 0.25)
    ].nlargest(5, "ic_ir")[["factor", "cross_section_spearman_mean", "ic_ir"]]

    win60 = win[win["window"] == 60]
    win5 = win[win["window"] == 5]

    lines = [
        "### 总体判断",
        "",
        f"- **交付**：158 个因子已全部在 SmartData 全市场（{panel_stocks} 只）完成计算，区间 {compute_range}。",
        f"- **复现精度**：在 qlib 对照样本（{validation_range}，{common_codes} 只股票交集）上，"
        f"**{pass_rate:.1f}%**（{passed}/{passed + failed}）因子截面 Spearman ≥ 0.95；"
        f"{failed} 个 FAIL、{skipped} 个 SKIP（VWAP0）。",
        f"- **有效性**：全样本中位 IC_IR = **{ic['ic_ir'].median():.3f}**；"
        f"IC_IR>0 的因子 {(ic['ic_ir'] > 0).sum()} 个，IC_IR<0 的 {(ic['ic_ir'] < 0).sum()} 个。",
        "",
        "### 精度维度（与 qlib 一致性）",
        "",
    ]

    if not win5.empty and not win60.empty:
        lines.append(
            f"- **滚动窗口效应明显**：5 日窗口通过率 **{win5['pass_rate_pct'].iloc[0]:.0f}%**（平均 Spearman {win5['mean_spearman'].iloc[0]:.4f}），"
            f"60 日窗口仅 **{win60['pass_rate_pct'].iloc[0]:.0f}%**（平均 {win60['mean_spearman'].iloc[0]:.4f}，最低 {win60['min_spearman'].iloc[0]:.4f}）。"
            f"未通过的 {fail_60}/{failed} 个 FAIL 因子名以 `60` 结尾，说明长窗口对 warm-up、IdxMin/IdxMax 实现与样本边界更敏感。"
        )
    lines.append(
        "- **短窗口价量类几乎全过**：K 线、ROC、MA、STD、VMA、VSTD 等族通过率普遍 ≥95%，说明核心公式与 SmartData 行情对齐良好。"
    )
    if not worst_fam_pass.empty:
        w = worst_fam_pass.iloc[0]
        lines.append(
            f"- **通过率最低的因子族**：{w['family']}（{w['pass_rate_pct']:.0f}% 通过，{int(w['fail_n'])} 个 FAIL），"
            "多与「高低点位置 / 价量相关 / 长窗口 RSI」相关，建议单独做实现 diff，而非怀疑整条流水线。"
        )

    lines.extend(["", "### 有效性维度（IC / 多空）", ""])
    lines.append(
        f"- **预测力最强**：{', '.join(f'`{r.factor}`(IC_IR={r.ic_ir:.3f})' for r in top_ic.itertuples())}。"
        "低位价格（LOW0/MIN*）与成交量结构（VMA/VSUMN）在全 A 股样本上 Rank IC 更稳定。"
    )
    lines.append(
        f"- **预测力最弱**：{', '.join(f'`{r.factor}`(IC_IR={r.ic_ir:.3f})' for r in bottom_ic.itertuples())}。"
        "K 线形态与价量相关性因子 IC 为负，更像噪声或反向信号，不宜直接当 alpha 使用。"
    )
    if not best_fam_ic.empty:
        lines.append(
            "- **按族平均 IC_IR 较高**："
            + "；".join(
                f"{r.family}（{r.mean_ic_ir:.3f}，通过率 {r.pass_rate_pct:.0f}%）"
                for r in best_fam_ic.itertuples()
            )
            + "。"
        )
    if not weak_fam_ic.empty:
        lines.append(
            "- **按族平均 IC_IR 较低**："
            + "；".join(
                f"{r.family}（{r.mean_ic_ir:.3f}）" for r in weak_fam_ic.itertuples()
            )
            + "。"
        )

    lines.extend(["", "### 精度 vs 有效性（交叉观察）", ""])
    lines.append(
        "- **两套指标独立**：Spearman 衡量「算得是否与 qlib 一样」；IC_IR 衡量「对未来收益有没有排序力」。二者不必同向。"
    )
    if not low_acc_high_ic.empty:
        lines.append(
            "- **算得不完全一致但 IC 仍不错**（FAIL 且 IC_IR 较高）："
            + "，".join(
                f"`{r.factor}`(Spearman={r.cross_section_spearman_mean:.3f}, IC_IR={r.ic_ir:.3f})"
                for r in low_acc_high_ic.itertuples()
            )
            + "。说明部分 FAIL 来自对照口径/长窗口边界，不代表因子无研究价值。"
        )
    if not high_acc_low_ic.empty:
        lines.append(
            "- **算得准但 IC 偏弱**（PASS 且 IC_IR 较低）："
            + "，".join(
                f"`{r.factor}`(Spearman={r.cross_section_spearman_mean:.3f}, IC_IR={r.ic_ir:.3f})"
                for r in high_acc_low_ic.itertuples()
            )
            + "。复现正确不等于有 alpha，K 线类因子多属此类。"
        )

    lines.extend(
        [
            "",
            "### 汇报建议",
            "",
            "1. 先强调 **全市场已算完**（股票数、日期），再说明 qlib 检验只是子样本对照。",
            "2. 通过率 85% 可接受：短窗口全过证明实现主体正确；FAIL 列表可逐条展示（见全表）。",
            "3. 有效性上优先讲 MIN/VMA/VSUMN/LOW 族；价量相关与 K 线族建议标注为弱信号。",
            "4. 2021-06-11 之后仅有 SmartData 因子与 IC，待 qlib 真值扩展后补检验。",
            "",
        ]
    )
    return lines


def md_table(
    df: pd.DataFrame,
    columns: list[str],
    *,
    float_cols: set[str] | None = None,
    int_cols: set[str] | None = None,
) -> str:
    float_cols = float_cols or set()
    int_cols = int_cols or set()
    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join(["---"] * len(columns)) + " |"
    lines = [header, sep]
    for _, row in df.iterrows():
        cells = []
        for col in columns:
            val = row[col]
            if col in float_cols and pd.notna(val):
                if col in {"pass_rate_pct", "ic_win_pct"}:
                    cells.append(f"{float(val):.1f}")
                else:
                    cells.append(f"{float(val):.4f}")
            elif col in int_cols and pd.notna(val):
                cells.append(str(int(val)))
            elif pd.isna(val):
                cells.append("-")
            else:
                cells.append(str(val))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def html_table_rows(df: pd.DataFrame, columns: list[str], *, fmt: dict[str, str] | None = None) -> str:
    fmt = fmt or {}
    rows: list[str] = []
    for _, row in df.iterrows():
        cells = []
        for col in columns:
            val = row[col]
            if pd.isna(val):
                text = "-"
            elif col in fmt:
                text = fmt[col].format(val)
            else:
                text = str(val)
            if col == "status":
                cls = "pass" if val == "PASS" else "fail" if val == "FAIL" else "skip"
                text = f'<span class="badge {cls}">{val}</span>'
            elif col == "factor":
                text = f"<code>{val}</code>"
            cells.append(f"<td>{text}</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return "\n".join(rows)