"""生成 Alpha158 中文汇报仪表盘（HTML + 大图 + 完整数据表 + 分析解读）。"""

from __future__ import annotations

import base64
import json
import re
from datetime import datetime
from io import BytesIO
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import patheffects as pe
from matplotlib.gridspec import GridSpec

from research_core.alpha158_lab.config import Alpha158ResearchConfig
from research_core.alpha158_lab.factors.specs import ALPHA158_BATCHES
from research_core.alpha158_lab.research.batch_report import build_mosaic
from research_core.alpha158_lab.research.master_insights import (
    build_analysis_narrative,
    build_merged_table,
    enrich_accuracy,
    enrich_ic,
    family_summary,
    html_table_rows,
    window_summary,
)
from research_core.factor_library.validation import summarize_ic

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / "runtime" / "alpha158_lab"
OUT = ROOT / "reports" / "master"

plt.rcParams.update(
    {
        "font.sans-serif": ["Microsoft YaHei", "SimHei", "DejaVu Sans"],
        "axes.unicode_minus": False,
        "figure.facecolor": "#FAFBFC",
        "axes.facecolor": "#FFFFFF",
        "axes.edgecolor": "#D0D7DE",
        "axes.labelcolor": "#24292F",
        "text.color": "#24292F",
        "xtick.color": "#57606A",
        "ytick.color": "#57606A",
        "grid.color": "#EAEEF2",
        "grid.linestyle": "--",
        "grid.alpha": 0.8,
    }
)

PALETTE = {
    "pass": "#2DA44E",
    "fail": "#CF222E",
    "skip": "#8C959F",
    "accent": "#0969DA",
    "warn": "#BF8700",
    "muted": "#656D76",
}


def _setup_cn_font() -> None:
    from matplotlib import font_manager

    for name in ("Microsoft YaHei", "SimHei", "PingFang SC"):
        try:
            font_manager.findfont(name, fallback_to_default=False)
            plt.rcParams["font.sans-serif"] = [name, "DejaVu Sans"]
            return
        except Exception:
            continue


def _factor_family(name: str) -> str:
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


def _load_accuracy() -> pd.DataFrame:
    rows: list[dict] = []
    root_report = ROOT / "validation" / "accuracy_report.json"
    if root_report.exists():
        for row in json.loads(root_report.read_text(encoding="utf-8")).get("factors", []):
            r = dict(row)
            r["batch"] = "batch_01"
            rows.append(r)
    for batch_id in sorted(ALPHA158_BATCHES):
        if batch_id == "batch_01":
            continue
        path = ROOT / "validation" / batch_id / "accuracy_report.json"
        if path.exists():
            for row in json.loads(path.read_text(encoding="utf-8")).get("factors", []):
                r = dict(row)
                r["batch"] = batch_id
                rows.append(r)
    df = pd.DataFrame(rows)
    df["family"] = df["factor"].map(_factor_family)
    df["window"] = df["factor"].str.extract(r"(\d+)$")[0].astype("float")
    return df


def _load_ic() -> pd.DataFrame:
    ic = pd.read_csv(ROOT / "effectiveness" / "ic_series.csv", parse_dates=["date"])
    summary = summarize_ic(ic).rename(
        columns={"mean_ic": "ic_mean", "ic_ir": "ic_ir", "win_rate": "ic_win_rate"}
    )
    batch_map = {
        f: b
        for b, m in ALPHA158_BATCHES.items()
        for f in m["factors"]  # type: ignore[union-attr]
    }
    summary["batch"] = summary["factor"].map(batch_map)
    summary["family"] = summary["factor"].map(_factor_family)
    summary["ic_win_pct"] = summary["ic_win_rate"] * 100
    return summary


def _img_to_b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def plot_overview_board(acc: pd.DataFrame, ic: pd.DataFrame, out: Path) -> Path:
    actionable = acc[acc["status"] != "SKIP"]
    passed = (actionable["status"] == "PASS").sum()
    failed = (actionable["status"] == "FAIL").sum()
    skipped = (acc["status"] == "SKIP").sum()

    fig = plt.figure(figsize=(16, 10))
    gs = GridSpec(2, 2, figure=fig, hspace=0.32, wspace=0.22)

    # 1) 复现结果饼图
    ax1 = fig.add_subplot(gs[0, 0])
    sizes = [passed, failed, skipped]
    labels = [f"通过 {passed}", f"未通过 {failed}", f"跳过 {skipped}"]
    colors = [PALETTE["pass"], PALETTE["fail"], PALETTE["skip"]]
    wedges, texts, autotexts = ax1.pie(
        sizes,
        labels=labels,
        colors=colors,
        autopct=lambda p: f"{p:.1f}%" if p > 0 else "",
        startangle=90,
        textprops={"fontsize": 11},
    )
    for t in autotexts:
        t.set_fontsize(10)
        t.set_path_effects([pe.withStroke(linewidth=2, foreground="white")])
    ax1.set_title("① qlib 复现结果（158 因子）", fontsize=14, fontweight="bold", pad=12)

    # 2) 因子族通过率
    ax2 = fig.add_subplot(gs[0, 1])
    fam = (
        actionable.groupby("family")
        .apply(
            lambda g: pd.Series({"通过率": (g["status"] == "PASS").mean() * 100, "数量": len(g)}),
            include_groups=False,
        )
        .reset_index()
        .sort_values("通过率", ascending=True)
    )
    bars = ax2.barh(fam["family"], fam["通过率"], color=np.where(fam["通过率"] >= 95, PALETTE["pass"], PALETTE["warn"]))
    ax2.axvline(95, color=PALETTE["fail"], linestyle="--", linewidth=1.2, label="阈值 95%")
    ax2.set_xlim(0, 105)
    ax2.set_xlabel("通过率 (%)")
    ax2.set_title("② 各因子族 qlib 通过率", fontsize=14, fontweight="bold", pad=12)
    ax2.legend(loc="lower right", fontsize=9)
    for bar, n in zip(bars, fam["数量"]):
        ax2.text(bar.get_width() + 1, bar.get_y() + bar.get_height() / 2, f"{n}个", va="center", fontsize=8, color=PALETTE["muted"])

    # 3) IC 最强因子
    ax3 = fig.add_subplot(gs[1, 0])
    top = ic.nlargest(12, "ic_ir").sort_values("ic_ir")
    colors_ic = [PALETTE["pass"] if v >= 0 else PALETTE["fail"] for v in top["ic_ir"]]
    ax3.barh(top["factor"], top["ic_ir"], color=colors_ic)
    ax3.axvline(0, color=PALETTE["muted"], linewidth=1)
    ax3.set_xlabel("IC_IR（日频 Rank IC）")
    ax3.set_title("③ 预测力最强 Top12 因子", fontsize=14, fontweight="bold", pad=12)

    # 4) 滚动窗口 vs 精度
    ax4 = fig.add_subplot(gs[1, 1])
    win = (
        actionable.dropna(subset=["window"])
        .groupby("window")
        .agg(通过率=("status", lambda s: (s == "PASS").mean() * 100), 平均Spearman=("cross_section_spearman_mean", "mean"))
        .reset_index()
        .sort_values("window")
    )
    x = win["window"].astype(int).astype(str)
    ax4.bar(x, win["通过率"], color=PALETTE["accent"], alpha=0.85, label="通过率")
    ax4.axhline(95, color=PALETTE["fail"], linestyle="--", linewidth=1.2)
    ax4.set_ylabel("通过率 (%)")
    ax4.set_xlabel("滚动窗口（交易日）")
    ax4.set_ylim(0, 105)
    ax4.set_title("④ 窗口越长，warm-up 影响越大", fontsize=14, fontweight="bold", pad=12)
    ax4b = ax4.twinx()
    ax4b.plot(x, win["平均Spearman"], color=PALETTE["warn"], marker="o", linewidth=2, label="平均 Spearman")
    ax4b.set_ylabel("平均 Spearman")
    ax4b.set_ylim(0.75, 1.0)
    lines1, lab1 = ax4.get_legend_handles_labels()
    lines2, lab2 = ax4b.get_legend_handles_labels()
    ax4.legend(lines1 + lines2, lab1 + lab2, loc="lower left", fontsize=8)

    fig.suptitle("Alpha158 一页总览", fontsize=18, fontweight="bold", y=0.98)
    fig.text(
        0.5,
        0.01,
        "说明：85% 因子与 qlib 一致；未通过集中在 60 日长窗口因子，与实现细节/对照样本有关。",
        ha="center",
        fontsize=10,
        color=PALETTE["muted"],
    )
    path = out / "01_一页总览.png"
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_batch_heatmap(acc: pd.DataFrame, ic: pd.DataFrame, out: Path) -> Path:
    batches = sorted(ALPHA158_BATCHES)
    rows = []
    for i, batch_id in enumerate(batches, start=1):
        factors = list(ALPHA158_BATCHES[batch_id]["factors"])  # type: ignore[arg-type]
        sub_acc = acc[acc["factor"].isin(factors) & (acc["status"] != "SKIP")]
        sub_ic = ic[ic["factor"].isin(factors)]
        rows.append(
            {
                "批次": f"#{i:02d}",
                "通过率": (sub_acc["status"] == "PASS").mean() * 100 if len(sub_acc) else 0,
                "平均Spearman": sub_acc["cross_section_spearman_mean"].mean() if len(sub_acc) else np.nan,
                "平均IC_IR": sub_ic["ic_ir"].mean() if len(sub_ic) else np.nan,
            }
        )
    df = pd.DataFrame(rows)

    fig, axes = plt.subplots(1, 3, figsize=(15, 5.5))
    metrics = [
        ("通过率", "qlib 通过率 (%)", (0, 105), PALETTE["pass"]),
        ("平均Spearman", "平均 Spearman", (0.85, 1.0), PALETTE["accent"]),
        ("平均IC_IR", "平均 IC_IR", None, PALETTE["warn"]),
    ]
    for ax, (col, title, ylim, color) in zip(axes, metrics):
        vals = df[col]
        bar_colors = [PALETTE["pass"] if (col == "通过率" and v >= 95) or (col != "通过率" and v >= 0) else PALETTE["fail"] for v in vals]
        if col == "通过率":
            bar_colors = [PALETTE["pass"] if v >= 90 else PALETTE["warn"] if v >= 70 else PALETTE["fail"] for v in vals]
        ax.bar(df["批次"], vals, color=bar_colors if col == "通过率" else color, alpha=0.9)
        ax.set_title(title, fontsize=12, fontweight="bold")
        ax.set_xlabel("批次")
        ax.tick_params(axis="x", rotation=45)
        if ylim:
            ax.set_ylim(*ylim)
        if col == "通过率":
            ax.axhline(95, color=PALETTE["fail"], linestyle="--", linewidth=1)
        if col == "平均IC_IR":
            ax.axhline(0, color=PALETTE["muted"], linestyle="--", linewidth=1)
        ax.grid(axis="y", alpha=0.4)

    fig.suptitle("16 个批次进度一览", fontsize=16, fontweight="bold")
    path = out / "02_批次进度.png"
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_scope_explain(cfg: Alpha158ResearchConfig, universe: dict[str, int], out: Path) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(14, 4.2))
    for ax in axes:
        ax.set_xlim(0, 10)
        ax.set_ylim(0, 10)
        ax.axis("off")

    # 左：计算口径
    ax = axes[0]
    rect = plt.Rectangle((0.8, 2.2), 8.4, 6.2, facecolor="#E8F5E9", edgecolor=PALETTE["pass"], linewidth=2)
    ax.add_patch(rect)
    ax.text(5, 7.4, "因子计算（生产口径）", ha="center", fontsize=14, fontweight="bold", color=PALETTE["pass"])
    ax.text(5, 6.2, f"股票：{universe['panel_stocks']:,} 只 A 股", ha="center", fontsize=12)
    ax.text(5, 5.2, f"日期：{cfg.compute_range_label}", ha="center", fontsize=12)
    ax.text(5, 4.0, "数据源：SmartData 全市场日线", ha="center", fontsize=11, color=PALETTE["muted"])
    ax.text(5, 2.8, "不与 qlib 取交集", ha="center", fontsize=11, color=PALETTE["muted"])

    # 右：检验口径
    ax = axes[1]
    rect = plt.Rectangle((0.8, 2.2), 8.4, 6.2, facecolor="#FFF8E1", edgecolor=PALETTE["warn"], linewidth=2)
    ax.add_patch(rect)
    ax.text(5, 7.4, "精度检验（对照口径）", ha="center", fontsize=14, fontweight="bold", color=PALETTE["warn"])
    ax.text(5, 6.2, f"股票：{universe['qlib_common']} 只（与 qlib 交集）", ha="center", fontsize=12)
    ax.text(5, 5.2, f"日期：{cfg.overlap_start} ~ {cfg.overlap_end}", ha="center", fontsize=12)
    ax.text(5, 4.0, "真值：本地 qlib cn_data（仅 {0} 只）".format(universe["qlib_truth"]), ha="center", fontsize=11, color=PALETTE["muted"])
    ax.text(5, 2.8, "阈值：截面 Spearman ≥ 0.95", ha="center", fontsize=11, color=PALETTE["muted"])

    fig.suptitle("两套口径：先算全市场，再在小样本上与 qlib 对照", fontsize=16, fontweight="bold", y=1.02)
    path = out / "03_口径说明.png"
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return path


def build_highlight_mosaic(ic: pd.DataFrame, out: Path) -> Path | None:
    top6 = ic.nlargest(6, "ic_ir")["factor"].tolist()
    path = out / "04_强势因子拼图.png"
    built = build_mosaic(
        factor_names=top6,
        charts_dir=ROOT / "charts",
        chart_suffix="ic_series",
        output_path=path,
        ncol=3,
        nrow=2,
    )
    if built:
        # 给拼图加中文标题：重新打开加 suptitle 太麻烦，单独说明在 HTML
        return path
    return None


def _html_card(title: str, value: str, subtitle: str, color: str) -> str:
    return f"""
    <div class="card" style="border-top: 4px solid {color}">
      <div class="card-label">{title}</div>
      <div class="card-value">{value}</div>
      <div class="card-sub">{subtitle}</div>
    </div>"""


def _resolve_truth_parquet(batch_id: str = "batch_16") -> Path:
    truth_dir = ROOT / "truth" / batch_id
    candidates = sorted(truth_dir.glob("qlib_truth_*.parquet"))
    if not candidates:
        raise FileNotFoundError(f"No qlib truth parquet under {truth_dir}")
    return candidates[-1]


def _sync_cfg_from_panel(cfg: Alpha158ResearchConfig) -> Alpha158ResearchConfig:
    panel_path = ROOT / "market_panel.parquet"
    if panel_path.exists():
        panel = pd.read_parquet(panel_path, columns=["date"])
        panel["date"] = pd.to_datetime(panel["date"])
        cfg.start_date = str(panel["date"].min().date())
        cfg.end_date = str(panel["date"].max().date())
    return cfg


def _universe_stats(cfg: Alpha158ResearchConfig) -> dict[str, int]:
    panel = pd.read_parquet(ROOT / "market_panel.parquet")
    truth = pd.read_parquet(_resolve_truth_parquet("batch_16"))
    panel["date"] = pd.to_datetime(panel["date"])
    truth["date"] = pd.to_datetime(truth["date"])
    start, end = pd.Timestamp(cfg.overlap_start), pd.Timestamp(cfg.overlap_end)
    panel_ov = panel[(panel["date"] >= start) & (panel["date"] <= end)]
    truth_ov = truth[(truth["date"] >= start) & (truth["date"] <= end)]

    def _is_stock(code: str) -> bool:
        return code.startswith(("SH6", "SZ0", "SZ3", "BJ"))

    return {
        "panel_total": int(panel["code"].nunique()),
        "panel_stocks": int(panel.loc[panel["code"].map(_is_stock), "code"].nunique()),
        "panel_overlap": int(panel_ov["code"].nunique()),
        "qlib_truth": int(truth_ov["code"].nunique()),
        "qlib_common": int(len(set(panel_ov["code"]) & set(truth_ov["code"]))),
    }


def _batch_status_table(actionable: pd.DataFrame) -> str:
    rows: list[str] = []
    for i, batch_id in enumerate(sorted(ALPHA158_BATCHES), start=1):
        factors = list(ALPHA158_BATCHES[batch_id]["factors"])  # type: ignore[arg-type]
        sub = actionable[actionable["factor"].isin(factors)]
        p = int((sub["status"] == "PASS").sum())
        f = int((sub["status"] == "FAIL").sum())
        rate = p / len(sub) * 100 if len(sub) else 0
        if rate >= 100:
            badge = '<span class="badge pass">全通过</span>'
        elif rate >= 90:
            badge = '<span class="badge warn">基本通过</span>'
        else:
            badge = '<span class="badge fail">需关注</span>'
        title = str(ALPHA158_BATCHES[batch_id]["batch_title"]).split("：", 1)[-1]
        rows.append(
            f"<tr><td>#{i:02d}</td><td>{title}</td><td>{p}</td><td>{f}</td>"
            f"<td><b>{rate:.0f}%</b></td><td>{badge}</td>"
            f'<td><a href="../{batch_id}/REPORT.md">明细</a></td></tr>'
        )
    return "\n".join(rows)


def _fail_factor_rows(actionable: pd.DataFrame) -> str:
    fails = actionable[actionable["status"] == "FAIL"].sort_values("cross_section_spearman_mean")
    if fails.empty:
        return "<tr><td colspan='4'>无</td></tr>"
    rows = []
    for row in fails.itertuples():
        rows.append(
            f"<tr><td><code>{row.factor}</code></td><td>{row.family}</td>"
            f"<td>{row.cross_section_spearman_mean:.3f}</td>"
            f"<td>{(1 - row.cross_section_spearman_mean):.1%}</td></tr>"
        )
    return "\n".join(rows)


def _md_inline_to_html(text: str) -> str:
    import re as _re

    text = _re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = _re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    return text


def _analysis_html(
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
) -> str:
    lines = build_analysis_narrative(
        acc=acc,
        ic=ic,
        pass_rate=pass_rate,
        passed=passed,
        failed=failed,
        skipped=skipped,
        panel_stocks=panel_stocks,
        common_codes=common_codes,
        compute_range=compute_range,
        validation_range=validation_range,
    )
    parts: list[str] = []
    for line in lines:
        if line.startswith("### "):
            parts.append(f"<h3>{_md_inline_to_html(line[4:])}</h3>")
        elif line.startswith("- "):
            parts.append(f"<li>{_md_inline_to_html(line[2:])}</li>")
        elif re.match(r"^\d+\.\s", line):
            parts.append(f"<li>{_md_inline_to_html(line[line.index('.') + 2:])}</li>")
        elif line.strip() == "":
            continue
        else:
            parts.append(f"<p>{_md_inline_to_html(line)}</p>")
    if parts and parts[-1].startswith("<li>"):
        parts.append("</ul>")
    html = []
    in_list = False
    for p in parts:
        if p.startswith("<li>"):
            if not in_list:
                html.append("<ul class='clean'>")
                in_list = True
            html.append(p)
        else:
            if in_list:
                html.append("</ul>")
                in_list = False
            html.append(p)
    if in_list:
        html.append("</ul>")
    return "\n".join(html)


def build_html(
    *,
    cfg: Alpha158ResearchConfig,
    acc: pd.DataFrame,
    ic: pd.DataFrame,
    images: dict[str, Path],
    mosaic_path: Path | None,
    universe: dict[str, int],
) -> str:
    acc = enrich_accuracy(acc)
    ic = enrich_ic(ic)
    merged = build_merged_table(acc, ic)
    fam_df = family_summary(acc, ic)
    win_df = window_summary(acc)

    actionable = acc[acc["status"] != "SKIP"]
    passed = int((actionable["status"] == "PASS").sum())
    failed = int((actionable["status"] == "FAIL").sum())
    skipped = int((acc["status"] == "SKIP").sum())
    pass_rate = passed / len(actionable) * 100 if len(actionable) else 0

    top20 = ic.nlargest(20, "ic_ir")
    bottom20 = ic.nsmallest(20, "ic_ir")
    fail_fam = (
        actionable[actionable["status"] == "FAIL"]
        .groupby("family")
        .size()
        .sort_values(ascending=False)
        .head(5)
    )
    fail_60d = int(
        actionable[actionable["status"] == "FAIL"]["factor"].str.endswith("60").sum()
    )

    img_tags = {
        k: f'<img src="data:image/png;base64,{_img_to_b64(p)}" alt="{k}"/>'
        for k, p in images.items()
        if p.exists()
    }
    mosaic_tag = ""
    if mosaic_path and mosaic_path.exists():
        mosaic_tag = f'<img src="data:image/png;base64,{_img_to_b64(mosaic_path)}" alt="强势因子"/>'

    fail_list = "".join(
        f"<li><b>{fam}</b>：{cnt} 个</li>" for fam, cnt in fail_fam.items()
    )
    top20_rows = html_table_rows(
        top20[["factor", "family", "batch", "ic_mean", "ic_ir", "ic_win_pct"]],
        ["factor", "family", "batch", "ic_mean", "ic_ir", "ic_win_pct"],
        fmt={"ic_mean": "{:.4f}", "ic_ir": "{:.4f}", "ic_win_pct": "{:.1f}"},
    )
    bottom20_rows = html_table_rows(
        bottom20[["factor", "family", "batch", "ic_mean", "ic_ir", "ic_win_pct"]],
        ["factor", "family", "batch", "ic_mean", "ic_ir", "ic_win_pct"],
        fmt={"ic_mean": "{:.4f}", "ic_ir": "{:.4f}", "ic_win_pct": "{:.1f}"},
    )
    fam_rows = html_table_rows(
        fam_df,
        ["family", "n", "pass_n", "fail_n", "pass_rate_pct", "mean_spearman", "mean_ic_ir", "median_ic_ir"],
        fmt={"pass_rate_pct": "{:.1f}", "mean_spearman": "{:.4f}", "mean_ic_ir": "{:.4f}", "median_ic_ir": "{:.4f}"},
    )
    win_rows = html_table_rows(
        win_df,
        ["window", "n", "pass_n", "fail_n", "pass_rate_pct", "mean_spearman", "min_spearman"],
        fmt={"pass_rate_pct": "{:.1f}", "mean_spearman": "{:.4f}", "min_spearman": "{:.4f}", "window": "{:.0f}"},
    )
    full_rows = html_table_rows(
        merged.sort_values(["batch", "factor"])[
            [
                "factor",
                "batch",
                "family",
                "window",
                "status",
                "cross_section_spearman_mean",
                "deviation_rate",
                "ic_mean",
                "ic_ir",
                "ic_win_pct",
            ]
        ],
        [
            "factor",
            "batch",
            "family",
            "window",
            "status",
            "cross_section_spearman_mean",
            "deviation_rate",
            "ic_mean",
            "ic_ir",
            "ic_win_pct",
        ],
        fmt={
            "cross_section_spearman_mean": "{:.4f}",
            "deviation_rate": "{:.4f}",
            "ic_mean": "{:.4f}",
            "ic_ir": "{:.4f}",
            "ic_win_pct": "{:.1f}",
            "window": "{:.0f}",
        },
    )

    analysis_block = _analysis_html(
        acc=acc,
        ic=ic,
        pass_rate=pass_rate,
        passed=passed,
        failed=failed,
        skipped=skipped,
        panel_stocks=universe["panel_stocks"],
        common_codes=universe["qlib_common"],
        compute_range=cfg.compute_range_label,
        validation_range=cfg.validation_range_label,
    )

    batch_table = _batch_status_table(actionable)
    fail_table = _fail_factor_rows(actionable)
    share_date = datetime.now().strftime("%Y-%m-%d")

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Alpha158 研究汇报 · 分享版</title>
  <style>
    :root {{
      --bg: #F6F8FA; --card: #FFFFFF; --text: #1F2328; --muted: #656D76;
      --border: #D8DEE4; --accent: #0969DA;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0; font-family: "Microsoft YaHei", "PingFang SC", sans-serif;
      background: var(--bg); color: var(--text); line-height: 1.65; font-size: 15px;
    }}
    .wrap {{ max-width: 1080px; margin: 0 auto; padding: 28px 24px 56px; }}
    .hero {{
      background: linear-gradient(135deg, #0550AE 0%, #0969DA 55%, #218BFF 100%);
      color: #fff; border-radius: 16px; padding: 32px 36px; margin-bottom: 20px;
    }}
    .hero .tag {{
      display: inline-block; background: rgba(255,255,255,.18); border-radius: 999px;
      padding: 4px 12px; font-size: 12px; margin-bottom: 10px;
    }}
    .hero h1 {{ margin: 0 0 10px; font-size: 30px; letter-spacing: .5px; }}
    .hero p {{ margin: 0; opacity: .94; font-size: 16px; max-width: 720px; }}
    nav.toc {{
      background: var(--card); border: 1px solid var(--border); border-radius: 12px;
      padding: 14px 18px; margin-bottom: 22px; font-size: 14px;
    }}
    nav.toc a {{ margin-right: 16px; text-decoration: none; color: var(--accent); }}
    .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 14px; margin-bottom: 24px; }}
    .card {{
      background: var(--card); border-radius: 12px; padding: 18px 20px;
      box-shadow: 0 1px 3px rgba(0,0,0,.06); border: 1px solid var(--border);
    }}
    .card-label {{ font-size: 13px; color: var(--muted); }}
    .card-value {{ font-size: 30px; font-weight: 700; margin: 6px 0 2px; }}
    .card-sub {{ font-size: 12px; color: var(--muted); line-height: 1.4; }}
    section {{
      background: var(--card); border: 1px solid var(--border); border-radius: 14px;
      padding: 24px 28px; margin-bottom: 22px;
    }}
    section h2 {{
      margin: 0 0 8px; font-size: 22px; display: flex; align-items: center; gap: 10px;
    }}
    section h2::before {{
      content: ""; width: 4px; height: 24px; background: var(--accent); border-radius: 2px;
    }}
    .lead {{ color: var(--muted); margin: 0 0 18px; font-size: 15px; }}
    .figure {{ text-align: center; margin: 16px 0; }}
    .figure img {{ max-width: 100%; border-radius: 10px; border: 1px solid var(--border); }}
    .two-col {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }}
    @media (max-width: 800px) {{ .two-col {{ grid-template-columns: 1fr; }} }}
    ul.clean {{ margin: 0; padding-left: 22px; }}
    ul.clean li {{ margin: 8px 0; }}
    .talking {{
      background: #F0F6FF; border-left: 4px solid var(--accent); border-radius: 0 10px 10px 0;
      padding: 16px 20px; margin: 0;
    }}
    .talking li {{ margin: 10px 0; }}
    .callout {{
      background: #FFF8C5; border: 1px solid #D4A72C; border-radius: 10px;
      padding: 14px 16px; font-size: 14px; margin-top: 14px;
    }}
    .callout.ok {{ background: #E8F5E9; border-color: #2DA44E; }}
    table.data {{
      width: 100%; border-collapse: collapse; font-size: 14px; margin-top: 8px;
    }}
    table.data th, table.data td {{
      border-bottom: 1px solid var(--border); padding: 10px 12px; text-align: left;
    }}
    table.data th {{ background: #F6F8FA; font-weight: 600; }}
    table.data tr:hover td {{ background: #FAFBFC; }}
    .badge {{
      display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: 12px; font-weight: 600;
    }}
    .badge.pass {{ background: #DAFBE1; color: #116329; }}
    .badge.warn {{ background: #FFF8C5; color: #7D4E00; }}
    .badge.fail {{ background: #FFEBE9; color: #A40E26; }}
    .badge.skip {{ background: #EFF1F3; color: #656D76; }}
    .scroll-table {{
      max-height: 520px; overflow: auto; border: 1px solid var(--border);
      border-radius: 10px; margin-top: 12px;
    }}
    .scroll-table table {{ margin: 0; }}
    .scroll-table thead th {{ position: sticky; top: 0; z-index: 1; }}
    .analysis-block h3 {{ font-size: 17px; margin: 20px 0 10px; color: var(--text); }}
    .analysis-block h3:first-child {{ margin-top: 0; }}
    .two-tables {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
    @media (max-width: 900px) {{ .two-tables {{ grid-template-columns: 1fr; }} }}
    .footer {{ text-align: center; color: var(--muted); font-size: 12px; margin-top: 28px; }}
    a {{ color: var(--accent); }}
    code {{ background: #EFF1F3; padding: 2px 6px; border-radius: 4px; font-size: 13px; }}
    @media print {{
      body {{ background: #fff; }}
      section {{ break-inside: avoid; box-shadow: none; }}
      nav.toc {{ display: none; }}
    }}
  </style>
</head>
<body>
<div class="wrap">
  <div class="hero">
    <div class="tag">周一分享 · {share_date}</div>
    <h1>Alpha158 全市场因子复现与有效性</h1>
    <p>158 个因子已在 SmartData 全市场完成计算（{cfg.compute_range_label}）；与 qlib 对照验证复制精度，并评估 IC 与多空表现。</p>
  </div>

  <nav class="toc">
    <b>目录：</b>
    <a href="#analysis">分析解读</a>
    <a href="#share">分享要点</a>
    <a href="#scope">数据口径</a>
    <a href="#overview">全局一览</a>
    <a href="#batches">批次进度</a>
    <a href="#family">因子族汇总</a>
    <a href="#ic-rank">IC 排行</a>
    <a href="#fails">未通过清单</a>
    <a href="#full-data">158 因子全表</a>
    <a href="#files">附录</a>
  </nav>

  <div class="cards">
    {_html_card("交付完成度", "158 / 158", "全部因子已计算并落库", PALETTE["accent"])}
    {_html_card("qlib 复现通过率", f"{pass_rate:.1f}%", f"{passed} 通过 · {failed} 未通过 · {skipped} 跳过", PALETTE["pass"])}
    {_html_card("计算股票池", f"{universe['panel_stocks']:,}", f"A 股标的 · 全品种 {universe['panel_total']:,}", PALETTE["muted"])}
    {_html_card("检验交集", f"{universe['qlib_common']}", f"仅检验时用 · qlib 仅 {universe['qlib_truth']} 只", PALETTE["warn"])}
    {_html_card("中位 IC_IR", f"{ic['ic_ir'].median():.3f}", "日频 Rank IC → 次日收益", PALETTE["warn"])}
  </div>

  <section id="analysis">
    <h2>分析解读</h2>
    <p class="lead">基于 158 因子精度与 IC 数据的自动归纳（非删减版，可与下方全表对照）</p>
    <div class="analysis-block">{analysis_block}</div>
  </section>

  <section id="share">
    <h2>分享要点（建议照着讲）</h2>
    <ul class="talking">
      <li><b>我们做了什么：</b>用 SmartData 在 <b>{universe['panel_stocks']:,}</b> 只 A 股、<b>{cfg.compute_range_label}</b> 上，复现了 qlib Alpha158 全部 158 个因子。</li>
      <li><b>算得准不准：</b><b>{pass_rate:.0f}%</b> 因子与 qlib 截面 Spearman ≥ 0.95；短窗口价量类几乎全过，未通过主要是 <b>60 日长窗口</b>（{fail_60d} 个）。</li>
      <li><b>两套口径：</b>计算用<b>全市场</b>；检验只在 <b>{universe['qlib_common']}</b> 只股票上与 qlib 对照——这不是算漏了股票，是本地 qlib 数据包覆盖有限。</li>
      <li><b>有没有 alpha：</b>低位价格（MIN*）、成交量均线（VMA*）、量能减量（VSUMN*）IC 相对更好；纯 K 线形态、价量相关类 IC 偏弱。</li>
      <li><b>后续：</b>2021-06-11 之后仅有 SmartData 计算与 IC，待 qlib 真值扩展后可补检验；60 日因子可单独做实现对齐。</li>
    </ul>
  </section>

  <section id="scope">
    <h2>数据口径（最容易被问到的）</h2>
    <div class="figure">{img_tags.get("scope", "")}</div>
    <table class="data">
      <tr><th>维度</th><th>因子计算</th><th>精度检验（5%）</th></tr>
      <tr><td>股票</td><td><b>{universe['panel_stocks']:,}</b> 只 A 股（全市场）</td><td><b>{universe['qlib_common']}</b> 只（与 qlib 交集）</td></tr>
      <tr><td>日期</td><td>{cfg.compute_range_label}</td><td>{cfg.overlap_start} ~ {cfg.overlap_end}</td></tr>
      <tr><td>数据源</td><td>SmartData 日线</td><td>qlib Alpha158 Handler</td></tr>
      <tr><td>通过标准</td><td>—</td><td>截面 Spearman ≥ 0.95</td></tr>
    </table>
    <div class="callout ok">
      <b>一句话：</b>{universe['qlib_common']} 是「对照样本数」，不是「只算了这么多只股票」。
    </div>
  </section>

  <section id="overview">
    <h2>一张图看懂全局</h2>
    <p class="lead">通过率 · 因子族稳定性 · 预测力 · 窗口长度与偏差关系</p>
    <div class="figure">{img_tags.get("overview", "")}</div>
  </section>

  <section id="batches">
    <h2>16 个批次进度</h2>
    <p class="lead">批次 01–05、14 全通过；06–13、15–16 有个别长窗口因子未过</p>
    <div class="figure">{img_tags.get("batch", "")}</div>
    <table class="data">
      <tr><th>批次</th><th>内容</th><th>过</th><th>败</th><th>通过率</th><th>状态</th><th></th></tr>
      {batch_table}
    </table>
  </section>

  <section id="family">
    <h2>按因子族汇总</h2>
    <p class="lead">同时看 qlib 通过率与平均 IC_IR，便于解释「算得准」与「有没有 alpha」</p>
    <table class="data">
      <tr><th>因子族</th><th>数量</th><th>过</th><th>败</th><th>通过率%</th><th>平均Spearman</th><th>平均IC_IR</th><th>中位IC_IR</th></tr>
      {fam_rows}
    </table>
    <h3 style="margin-top:24px">按滚动窗口</h3>
    <table class="data">
      <tr><th>窗口</th><th>数量</th><th>过</th><th>败</th><th>通过率%</th><th>平均Spearman</th><th>最低Spearman</th></tr>
      {win_rows}
    </table>
  </section>

  <section id="ic-rank">
    <h2>有效性排行（IC_IR Top / Bottom 20）</h2>
    <p class="lead">全样本日频 Rank IC；与 qlib Spearman 是独立指标</p>
    <div class="two-tables">
      <div>
        <h3>Top 20</h3>
        <table class="data">
          <tr><th>因子</th><th>族</th><th>批次</th><th>IC均值</th><th>IC_IR</th><th>胜率%</th></tr>
          {top20_rows}
        </table>
      </div>
      <div>
        <h3>Bottom 20</h3>
        <table class="data">
          <tr><th>因子</th><th>族</th><th>批次</th><th>IC均值</th><th>IC_IR</th><th>胜率%</th></tr>
          {bottom20_rows}
        </table>
      </div>
    </div>
    <div class="figure">{mosaic_tag}</div>
  </section>

  <section id="fails">
    <h2>未通过因子清单（共 {failed} 个）</h2>
    <p class="lead">按 Spearman 从低到高排列；{skipped} 个 SKIP（VWAP0：qlib 缺 $vwap 字段）</p>
    <div class="two-col">
      <div>
        <p class="lead"><b>按因子族：</b></p>
        <ul class="clean">{fail_list or "<li>无</li>"}</ul>
      </div>
      <div>
        <div class="callout">
          <b>怎么解释 FAIL：</b>不是流水线坏了。短窗口已通过说明公式主体正确；60 日类偏差更大，需单独对齐实现或接受对照口径限制。
        </div>
      </div>
    </div>
    <table class="data">
      <tr><th>因子</th><th>因子族</th><th>Spearman</th><th>偏差率</th></tr>
      {fail_table}
    </table>
  </section>

  <section id="full-data">
    <h2>158 因子完整数据表</h2>
    <p class="lead">精度（Spearman / 状态）+ 有效性（IC）合并视图；可滚动浏览全部 158 行</p>
    <div class="scroll-table">
      <table class="data">
        <tr>
          <th>因子</th><th>批次</th><th>族</th><th>窗口</th><th>状态</th>
          <th>Spearman</th><th>偏差率</th><th>IC均值</th><th>IC_IR</th><th>IC胜率%</th>
        </tr>
        {full_rows}
      </table>
    </div>
  </section>

  <section id="files">
    <h2>附录与明细</h2>
    <ul class="clean">
      <li><a href="MASTER_SUMMARY.md">MASTER_SUMMARY.md</a> — 完整 Markdown（含分析 + 全表，可打印）</li>
      <li><a href="merged_all.csv">merged_all.csv</a> — 158 因子精度+IC 合并 CSV</li>
      <li><a href="accuracy_all.csv">accuracy_all.csv</a> — qlib 精度</li>
      <li><a href="ic_summary_all.csv">ic_summary_all.csv</a> — IC 汇总</li>
      <li><a href="../batch_01/REPORT.md">batch_01 ~ batch_16 REPORT.md</a> — 分批次明细与小图</li>
    </ul>
  </section>

  <div class="footer">Alpha158 Lab · 生成于 {datetime.now().strftime("%Y-%m-%d %H:%M")}</div>
</div>
</body>
</html>"""


def main() -> None:
    _setup_cn_font()
    cfg = _sync_cfg_from_panel(Alpha158ResearchConfig())
    chart_dir = OUT / "dashboard"
    chart_dir.mkdir(parents=True, exist_ok=True)

    acc = enrich_accuracy(_load_accuracy())
    ic = enrich_ic(_load_ic())
    acc.to_csv(OUT / "accuracy_all.csv", index=False, encoding="utf-8-sig")
    ic.to_csv(OUT / "ic_summary_all.csv", index=False, encoding="utf-8-sig")
    build_merged_table(acc, ic).to_csv(OUT / "merged_all.csv", index=False, encoding="utf-8-sig")

    universe = _universe_stats(cfg)
    images = {
        "overview": plot_overview_board(acc, ic, chart_dir),
        "batch": plot_batch_heatmap(acc, ic, chart_dir),
        "scope": plot_scope_explain(cfg, universe, chart_dir),
    }
    mosaic = build_highlight_mosaic(ic, chart_dir)
    html = build_html(cfg=cfg, acc=acc, ic=ic, images=images, mosaic_path=mosaic, universe=universe)
    html_path = OUT / "MASTER_DASHBOARD.html"
    html_path.write_text(html, encoding="utf-8")

    payload = {
        "html": str(html_path.resolve()),
        "charts": {k: str(v.resolve()) for k, v in images.items()},
        "mosaic": str(mosaic.resolve()) if mosaic else None,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"\n请用浏览器打开: {html_path.resolve()}")


if __name__ == "__main__":
    main()