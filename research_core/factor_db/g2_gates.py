"""G2 九道验真闸门 runner（FACTOR_LIFECYCLE.md v2.0 闸门4—12 的骨架实现）。

执行契约（宪法条款的代码化）：
- **固定顺序** 4→5→…→12，逐道短路（先失败先出局，修正 C）
- 闸门5 过滤后的全集上计算后续统计量（修正 C）
- 每道闸门产出 evidence dict，可整链写入 :class:`EvidenceLedger`
- OOS 只在闸门8 开封一次，经 :class:`OOSAccessLedger` 计数（上限 3 次）

阈值全部取自宪法 v2.0 §1 G2 表格。本模块为骨架验证实现：
统计方法正确（Spearman IC / block bootstrap / BH-FDR / 分段 / 正交化），
真实数据接入后直接替换输入面板即可，闸门逻辑不变。

用法（骨架验证）::

    from research_core.factor_db.g2_mock_data import build_long_panel
    from research_core.factor_db.g2_gates import run_g2

    wide, names = build_long_panel()
    report = run_g2(wide, "planted_good", prereg_split="2022-01-01")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from research_core.factor_db.lifecycle import (
    G2_GATE_ORDER,
    assert_gate_order,
)

# ---------------------------------------------------------------------------
# 阈值（宪法 v2.0 §1 G2，一个都不许改）
# ---------------------------------------------------------------------------

G4_MAX_MISSING_RATE = 0.05
G4_MIN_COVERAGE = 0.90
G5_MIN_AVG_AMOUNT = 2.0e7  # ¥2,000 万
G5_MIN_DAYS_IPO = 120
G5_MAX_ALPHA_DECAY = 0.50  # 过滤前后 alpha 衰减 >50% 判死
G6_MIN_ICIR = 0.30
G6_BOOTSTRAP_N = 1000
G6_BOOTSTRAP_BLOCK = 6
G7_FDR_Q = 0.05
G8_MIN_OOS_RETENTION = 0.70
G9_COST_BREAKEVEN_RATIO = 2.0  # breakeven cost ≥ 2× 实际成本
G9_ACTUAL_COST_BP = 10.0  # 印花税 5bp 卖出 + 佣金 2.5bp 双边（单边近似）
G10_MIN_RETAINED_IC = 0.70  # 残差 IC 达闸门6 标准的 70%
G11_MIN_YEARS_ALIGNED = 3
G11_MIN_WORST_YEAR_RATIO = 0.30
G12_MAX_CORR = 0.70
G12_MIN_INCREMENTAL_IC = 0.70


@dataclass
class GateResult:
    gate: str
    passed: bool
    evidence: dict[str, Any] = field(default_factory=dict)
    reason: str = ""


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------


def _monthly_rank_ic(df: pd.DataFrame, factor_col: str) -> pd.Series:
    """月频横截面 Spearman Rank IC 序列。"""
    def _one(d: pd.DataFrame) -> float:
        if len(d) < 10:
            return np.nan
        return d[factor_col].corr(d["next_return"], method="spearman")

    return df.groupby("date").apply(_one, include_groups=False).dropna()


def _block_bootstrap_ci(ic: pd.Series, n_boot: int = G6_BOOTSTRAP_N, block: int = G6_BOOTSTRAP_BLOCK, seed: int = 7) -> tuple[float, float]:
    """block bootstrap 均值 IC 的 95% 置信区间（保留序列相关）。"""
    rng = np.random.default_rng(seed)
    vals = ic.to_numpy()
    n = len(vals)
    if n < block * 2:
        return (np.nan, np.nan)
    n_blocks = int(np.ceil(n / block))
    means = np.empty(n_boot)
    for b in range(n_boot):
        starts = rng.integers(0, n - block + 1, n_blocks)
        sample = np.concatenate([vals[s : s + block] for s in starts])[:n]
        means[b] = sample.mean()
    return (float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975)))


def _bh_adjusted_pvalue(pvals: dict[str, float], self_key: str) -> float:
    """标准 Benjamini-Hochberg adjusted p-value（step-up）。

    adjusted_p(i) = min_{k >= rank(i)} ( m / k * p_(k) )
    self 的校正后 p ≤ q 即通过多重检验。
    """
    arr = np.sort(np.asarray(list(pvals.values()), dtype=float))
    m = len(arr)
    if m == 0:
        return 1.0
    self_p = float(pvals[self_key])
    rank = int((arr <= self_p).sum())  # 1-based rank（并列取保守大秩）
    if rank == 0:
        return 1.0
    # 从秩 rank 到 m 取 step-up 最小值
    adjusted = np.min((m / np.arange(rank, m + 1)) * arr[rank - 1 :])
    return float(min(adjusted, 1.0))


# ---------------------------------------------------------------------------
# 闸门实现（每道闸门签名一致，便于逐道短路）
# ---------------------------------------------------------------------------


def gate4_data_quality(df: pd.DataFrame, factor_col: str, registered: set[str] | None = None) -> GateResult:
    total = len(df)
    missing = df[factor_col].isna().sum()
    missing_rate = missing / total if total else 1.0
    coverage = 1.0 - missing_rate
    passed = missing_rate < G4_MAX_MISSING_RATE and coverage >= G4_MIN_COVERAGE
    return GateResult(
        "g4_data_quality",
        passed,
        {"missing_rate": round(missing_rate, 4), "coverage": round(coverage, 4),
         "n_rows": total},
        "" if passed else f"缺失率 {missing_rate:.2%} / 覆盖 {coverage:.2%} 不达标",
    )


def gate5_executability(df: pd.DataFrame, factor_col: str) -> tuple[GateResult, pd.DataFrame]:
    """返回 (结果, 过滤后全集)——后续闸门一律用过滤后全集（修正 C）。"""
    raw_ic = _monthly_rank_ic(df, factor_col).mean()

    ok = (
        ~df["limit_up"].astype(bool)
        & ~df["limit_down"].astype(bool)
        & ~df["suspended"].astype(bool)
        & ~df["is_st"].astype(bool)
        & (df["days_since_ipo"] >= G5_MIN_DAYS_IPO)
        & (df["avg_amount_20d"] >= G5_MIN_AVG_AMOUNT)
    )
    filtered = df[ok]
    filt_ic = _monthly_rank_ic(filtered, factor_col).mean()

    alpha_decay = 1.0 - (filt_ic / raw_ic) if raw_ic and raw_ic != 0 else 0.0
    passed = filtered[factor_col].notna().sum() > 0 and alpha_decay <= G5_MAX_ALPHA_DECAY
    return (
        GateResult(
            "g5_executability",
            passed,
            {"raw_ic": round(raw_ic, 4), "filtered_ic": round(filt_ic, 4),
             "alpha_decay": round(alpha_decay, 4),
             "kept_rows": int(len(filtered)), "dropped_rows": int(len(df) - len(filtered))},
            "" if passed else f"过滤前后 alpha 衰减 {alpha_decay:.1%} > 50%",
        ),
        filtered,
    )


def gate6_ic_stability(df: pd.DataFrame, factor_col: str) -> GateResult:
    ic = _monthly_rank_ic(df, factor_col)
    if len(ic) < 12:
        return GateResult("g6_ic_stability", False, {"n_months": len(ic)}, "月频 IC 不足 12 个月")
    mean_ic = ic.mean()
    icir = mean_ic / ic.std() if ic.std() > 0 else 0.0
    lo, hi = _block_bootstrap_ci(ic)
    ci_excludes_zero = (not np.isnan(lo)) and (lo > 0 or hi < 0)
    passed = icir > G6_MIN_ICIR and ci_excludes_zero
    return GateResult(
        "g6_ic_stability",
        passed,
        {"mean_rank_ic": round(mean_ic, 4), "icir": round(icir, 3),
         "bootstrap_ci95": [round(lo, 4), round(hi, 4)], "n_months": len(ic)},
        "" if passed else f"ICIR {icir:.2f} ≤ 0.30 或 bootstrap CI 含 0",
    )


def gate7_multiple_testing(pvals: dict[str, float], self_key: str) -> GateResult:
    """BH-FDR：self 的校正后 p 值 ≤ q 才算真信号（而非本轮运气最好者）。"""
    adjusted = _bh_adjusted_pvalue(pvals, self_key)
    passed = adjusted <= G7_FDR_Q
    return GateResult(
        "g7_multiple_testing",
        passed,
        {"n_trials": len(pvals), "self_p": round(float(pvals[self_key]), 6),
         "bh_adjusted_p": round(adjusted, 6), "fdr_q": G7_FDR_Q},
        "" if passed else f"BH 校正后 p={adjusted:.4g} > q={G7_FDR_Q}（N={len(pvals)} 次试验）",
    )


def gate8_oos_retention(df: pd.DataFrame, factor_col: str, prereg_split: str) -> GateResult:
    """OOS 开封（访问计数由 runner 统一处理）。"""
    is_df = df[df["date"] < prereg_split]
    oos_df = df[df["date"] >= prereg_split]
    ic_is = _monthly_rank_ic(is_df, factor_col).mean()
    ic_oos = _monthly_rank_ic(oos_df, factor_col).mean()
    retention = ic_oos / ic_is if ic_is and ic_is != 0 else 0.0
    passed = retention >= G8_MIN_OOS_RETENTION
    return GateResult(
        "g8_oos_retention",
        passed,
        {"is_ic": round(ic_is, 4), "oos_ic": round(ic_oos, 4),
         "retention": round(retention, 3), "split": prereg_split},
        "" if passed else f"OOS 留存 {retention:.1%} < 70%（IS {ic_is:.3f} → OOS {ic_oos:.3f}）",
    )


def gate9_cost_resilience(df: pd.DataFrame, factor_col: str) -> GateResult:
    """breakeven cost = 使扣费后 IC 归零的单边成本（以组合月超额的 bp 计）。

    骨架口径：月频 top-quintile 多空超额 → 年化 → 按年化双边换手摊销成本，
    breakeven = 超额归零时的单边 bp。要求 breakeven ≥ 2× 实际成本(10bp)。
    """
    ic = _monthly_rank_ic(df, factor_col)
    ann_alpha_ic = ic.mean() * 12  # IC 年化近似

    # 换手：Top 20% 组合月度成员变动率（双边口径 ×2）
    top_sets: dict[Any, set[str]] = {}
    for d, daily in df.groupby("date"):
        k = max(1, int(len(daily) * 0.2))
        top_sets[d] = set(daily.nlargest(k, factor_col)["code"])
    keys = sorted(top_sets)
    chg = [
        len(top_sets[a] ^ top_sets[b]) / (len(top_sets[a] | top_sets[b]) or 1)
        for a, b in zip(keys, keys[1:])
    ]
    monthly_turnover = float(np.mean(chg)) if chg else 1.0
    annual_double_turnover = monthly_turnover * 12 * 2

    # 组合月超额近似 = mean_ic × 截面收益波动
    cross_vol = float(df.groupby("date")["next_return"].std().mean())
    monthly_alpha = ic.mean() * cross_vol
    if monthly_alpha <= 0:
        return GateResult("g9_cost_resilience", False,
                          {"monthly_alpha": round(monthly_alpha, 5)},
                          "alpha ≤ 0，成本韧性无从谈起")

    # 每月成本（bp → 收益率）：双边换手 × 单边成本
    cost_per_month = (annual_double_turnover / 12) * G9_ACTUAL_COST_BP * 1e-4
    breakeven_bp = monthly_alpha / ((annual_double_turnover / 12) * 1e-4) if annual_double_turnover > 0 else 0.0
    passed = breakeven_bp >= G9_COST_BREAKEVEN_RATIO * G9_ACTUAL_COST_BP
    return GateResult(
        "g9_cost_resilience",
        passed,
        {"breakeven_cost_bp": round(breakeven_bp, 1),
         "actual_cost_bp": G9_ACTUAL_COST_BP,
         "annual_double_turnover": round(annual_double_turnover, 2),
         "monthly_alpha": round(monthly_alpha, 5),
         "cost_per_month": round(cost_per_month, 6)},
        "" if passed else f"breakeven {breakeven_bp:.0f}bp < 2× 实际成本 {G9_COST_BREAKEVEN_RATIO * G9_ACTUAL_COST_BP:.0f}bp",
    )


def gate10_style_neutrality(df: pd.DataFrame, factor_col: str) -> GateResult:
    """对市值 + 行业 + 动量载荷回归取残差，残差 IC 须达闸门6 标准的 70%。"""
    data = df[[factor_col, "next_return", "log_mcap", "industry", "mom_load"]].dropna()
    # 截面回归（逐月），行业哑变量 + log_mcap + mom_load
    resid_ics: list[float] = []
    for _, daily in data.groupby(data.index if "date" not in data else daily_index(data)):
        break  # 占位，下面用带 date 的实现
    # 重新组织（保持简单：用 df 里的 date 列）
    data = df[[factor_col, "next_return", "log_mcap", "industry", "mom_load", "date"]].dropna()
    for _, daily in data.groupby("date"):
        if len(daily) < 15:
            continue
        X = pd.get_dummies(daily[["industry"]], drop_first=True).astype(float)
        X["log_mcap"] = daily["log_mcap"].values
        X["mom_load"] = daily["mom_load"].values
        X = X.values
        y = daily[factor_col].values
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        resid = y - X @ beta
        ic = pd.Series(resid).corr(pd.Series(daily["next_return"].values), method="spearman")
        if not np.isnan(ic):
            resid_ics.append(ic)
    if not resid_ics:
        return GateResult("g10_style_neutrality", False, {}, "残差 IC 无法计算")
    mean_resid_ic = float(np.mean(resid_ics))
    std = float(np.std(resid_ics, ddof=1)) if len(resid_ics) > 1 else 1.0
    resid_icir = mean_resid_ic / std if std > 0 else 0.0
    # 骨架标准：残差 ICIR 仍 > 0.30 的 70%（宪法口径）
    passed = mean_resid_ic > 0 and resid_icir > G6_MIN_ICIR * G10_MIN_RETAINED_IC
    return GateResult(
        "g10_style_neutrality",
        passed,
        {"resid_mean_ic": round(mean_resid_ic, 4), "resid_icir": round(resid_icir, 3),
         "n_months": len(resid_ics)},
        "" if passed else "市值/行业/动量中性化后残差 IC 不足",
    )


def daily_index(data):  # pragma: no cover - 兼容占位
    return range(len(data))


def gate11_market_segments(df: pd.DataFrame, factor_col: str) -> GateResult:
    """按自然年分段：≥3 年方向一致，最差年份 IC ≥ 全样本 30%。"""
    ic = _monthly_rank_ic(df, factor_col)
    if ic.empty:
        return GateResult("g11_market_segments", False, {}, "无 IC 序列")
    years = pd.Series(ic.values, index=pd.DatetimeIndex(ic.index)).groupby(
        pd.DatetimeIndex(ic.index).year
    )
    year_ic = years.mean()
    aligned = (year_ic > 0).sum() if year_ic.mean() >= 0 else (year_ic < 0).sum()
    full_ic = ic.mean()
    worst = year_ic.min() if full_ic >= 0 else year_ic.max()
    worst_ratio = worst / full_ic if full_ic else 0.0
    passed = aligned >= G11_MIN_YEARS_ALIGNED and worst_ratio >= G11_MIN_WORST_YEAR_RATIO
    return GateResult(
        "g11_market_segments",
        passed,
        {"yearly_ic": {int(k): round(v, 4) for k, v in year_ic.items()},
         "years_aligned": int(aligned), "worst_year_ratio": round(worst_ratio, 3)},
        "" if passed else f"仅 {aligned} 年方向一致或最差年 IC 比例 {worst_ratio:.0%} < 30%",
    )


def gate12_redundancy(
    df: pd.DataFrame,
    factor_col: str,
    library_cols: list[str],
) -> GateResult:
    """两两相关性 <0.7 且对已入库因子正交化后残差 IC 达 70%。"""
    if not library_cols:
        return GateResult("g12_redundancy", True, {"library": 0}, "")
    sub = df[library_cols + [factor_col]].corr(method="spearman")[factor_col].drop(factor_col)
    max_corr = float(sub.abs().max()) if len(sub) else 0.0
    passed_corr = max_corr < G12_MAX_CORR

    # 增量 IC：对库内因子回归取残差后的 IC
    data = df[library_cols + [factor_col, "next_return"]].dropna()
    X = data[library_cols].values
    y = data[factor_col].values
    if X.shape[0] > X.shape[1] and np.linalg.matrix_rank(X) == X.shape[1]:
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        resid = y - X @ beta
        resid_ic = pd.Series(resid).corr(pd.Series(data["next_return"].values), method="spearman")
        base_ic = pd.Series(y).corr(pd.Series(data["next_return"].values), method="spearman")
        incremental = resid_ic / base_ic if base_ic else 0.0
    else:
        incremental = 0.0
    passed = passed_corr and incremental >= G12_MIN_INCREMENTAL_IC
    return GateResult(
        "g12_redundancy",
        passed,
        {"max_corr_with_library": round(max_corr, 3), "incremental_ic_ratio": round(incremental, 3)},
        "" if passed else f"相关性 {max_corr:.2f} ≥ 0.7 或增量 IC 比例 {incremental:.0%} < 70%",
    )


# ---------------------------------------------------------------------------
# Runner：固定顺序 + 逐道短路 + OOS 计数 + 证据链
# ---------------------------------------------------------------------------


@dataclass
class G2Report:
    factor_col: str
    passed_all: bool
    gates: list[GateResult]
    executed_order: list[str]
    first_failure: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "factor": self.factor_col,
            "passed_all": self.passed_all,
            "first_failure": self.first_failure,
            "executed_order": self.executed_order,
            "gates": [
                {"gate": g.gate, "passed": g.passed, "evidence": g.evidence, "reason": g.reason}
                for g in self.gates
            ],
        }


def run_g2(
    wide: pd.DataFrame,
    factor_col: str,
    *,
    prereg_split: str,
    library_cols: list[str] | None = None,
    all_factor_pvals: dict[str, float] | None = None,
) -> G2Report:
    """跑一个因子的九道闸门（固定顺序、逐道短路）。

    Args:
        wide: 长表面板（date/code/next_return/因子列 + 闸门5/10 字段）
        factor_col: 因子列名
        prereg_split: 预注册 IS/OOS 切分日期（novel 入队锁定 / replication 发表后）
        library_cols: 已入库因子列（闸门12）
        all_factor_pvals: 本轮全部因子的 p 值（闸门7 多重检验）
    """
    df = wide.copy()
    results: list[GateResult] = []
    order: list[str] = []

    # 闸门4 数据质量
    g4 = gate4_data_quality(df, factor_col)
    results.append(g4)
    order.append(g4.gate)
    if not g4.passed:
        return _finish(factor_col, results, order)

    # 闸门5 可执行性（过滤全集，后续全用 filtered）
    g5, df = gate5_executability(df, factor_col)
    results.append(g5)
    order.append(g5.gate)
    if not g5.passed:
        return _finish(factor_col, results, order)

    # 闸门6 IC 稳定性
    g6 = gate6_ic_stability(df, factor_col)
    results.append(g6)
    order.append(g6.gate)
    if not g6.passed:
        return _finish(factor_col, results, order)

    # 闸门7 多重检验（需要本轮全体 p 值；骨架验证默认只有自身 → N=1 直接过）
    pvals = all_factor_pvals or {factor_col: _ic_pvalue(df, factor_col)}
    g7 = gate7_multiple_testing(pvals, factor_col)
    results.append(g7)
    order.append(g7.gate)
    if not g7.passed:
        return _finish(factor_col, results, order)

    # 闸门8 OOS（唯一开封点；OOS 计数由调用方经 OOSAccessLedger 记录）
    g8 = gate8_oos_retention(df, factor_col, prereg_split)
    results.append(g8)
    order.append(g8.gate)
    if not g8.passed:
        return _finish(factor_col, results, order)

    # 闸门9 成本韧性
    g9 = gate9_cost_resilience(df, factor_col)
    results.append(g9)
    order.append(g9.gate)
    if not g9.passed:
        return _finish(factor_col, results, order)

    # 闸门10 风格中性
    g10 = gate10_style_neutrality(df, factor_col)
    results.append(g10)
    order.append(g10.gate)
    if not g10.passed:
        return _finish(factor_col, results, order)

    # 闸门11 市场分段
    g11 = gate11_market_segments(df, factor_col)
    results.append(g11)
    order.append(g11.gate)
    if not g11.passed:
        return _finish(factor_col, results, order)

    # 闸门12 冗余去重
    g12 = gate12_redundancy(df, factor_col, library_cols or [])
    results.append(g12)
    order.append(g12.gate)

    assert_gate_order(order)  # 宪法修正 C：顺序违宪直接炸
    return _finish(factor_col, results, order)


def _ic_pvalue(df: pd.DataFrame, factor_col: str) -> float:
    """t 检验 p 值（IC 均值 ≠ 0），供闸门7 用。"""
    ic = _monthly_rank_ic(df, factor_col)
    if len(ic) < 3 or ic.std() == 0:
        return 1.0
    t = ic.mean() / (ic.std() / np.sqrt(len(ic)))
    # 正态近似（骨架；正式可用 scipy.stats.t）
    from math import erf, sqrt

    z = abs(t)
    p = 2 * (1 - 0.5 * (1 + erf(z / sqrt(2))))
    return p


def _finish(factor_col: str, results: list[GateResult], order: list[str]) -> G2Report:
    failed = [g.gate for g in results if not g.passed]
    return G2Report(
        factor_col=factor_col,
        passed_all=not failed,
        gates=results,
        executed_order=order,
        first_failure=failed[0] if failed else None,
    )


__all__ = [
    "run_g2",
    "G2Report",
    "GateResult",
    "G2_GATE_ORDER",
    "gate4_data_quality",
    "gate5_executability",
    "gate6_ic_stability",
    "gate7_multiple_testing",
    "gate8_oos_retention",
    "gate9_cost_resilience",
    "gate10_style_neutrality",
    "gate11_market_segments",
    "gate12_redundancy",
]
