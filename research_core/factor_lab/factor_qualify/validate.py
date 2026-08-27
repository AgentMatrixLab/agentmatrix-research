"""
因子质量验证 — 纯因子层，不涉及策略参数

S0  IC筛选：信号存在性（IC强度 + 方向一致性 + 单调性）
S1  月度IC稳定性：信号在时序上是否持续显著
S2  CSCV/PBO：方向在时间切片上是否稳定（Lopez de Prado 2014）
S3  IC衰减建模：信号是否在消亡（Lee 2025）
S4  分位价差稳定性：截面多空价差是否持续存在
"""

from __future__ import annotations
import warnings
import numpy as np
import pandas as pd
from scipy.stats import spearmanr, linregress

warnings.filterwarnings("ignore")


# ═══════════════════════════════════════════════════════════════
# 工具
# ═══════════════════════════════════════════════════════════════

def compute_daily_ic(df, factor_col="factor_value", return_col="future_ret_5d"):
    rows = []
    for dt, g in df.groupby("date"):
        valid = g[[factor_col, return_col]].dropna()
        if len(valid) < 30: continue
        rows.append({"date": dt, "ic": float(spearmanr(valid[factor_col], valid[return_col])[0]),
                     "n_stocks": len(valid)})
    return pd.DataFrame(rows)


def _quantile_returns(df, factor_col, return_col, n_quantiles=5):
    data = df[[factor_col, return_col, "date"]].dropna().copy()
    results = {}
    for dt, g in data.groupby("date"):
        if len(g) < n_quantiles * 5: continue
        g["q"] = pd.qcut(g[factor_col], n_quantiles, labels=False, duplicates="drop")
        for q in range(n_quantiles):
            q_ret = g[g["q"] == q][return_col].mean()
            results.setdefault(q, []).append(q_ret)
    return {f"Q{q}": round(float(np.mean(results[q])), 6) if q in results else 0
            for q in range(n_quantiles)}


# ═══════════════════════════════════════════════════════════════
# S0 — IC筛选
# ═══════════════════════════════════════════════════════════════

def quick_filter(df, factor_col="factor_value", return_col="future_ret_5d"):
    """S0: IC + 方向一致性 + 单调性"""
    ic_df = compute_daily_ic(df, factor_col, return_col)
    ic_vals = ic_df["ic"].dropna().values
    if len(ic_vals) < 20: return {"passed": False, "error": f"只有 {len(ic_vals)} 个有效IC日"}

    ic_raw_mean = float(np.mean(ic_vals))
    ic_abs_mean = float(np.abs(ic_raw_mean))
    ic_std = float(np.std(ic_vals))
    icir_annual = float(ic_abs_mean / ic_std * np.sqrt(252)) if ic_std > 0 else 0
    ic_win_rate = float((ic_vals > 0).mean())
    directional_win = max(ic_win_rate, 1 - ic_win_rate)
    direction = "positive" if ic_raw_mean > 0 else "negative"

    q_returns = _quantile_returns(df, factor_col, return_col, 5)
    keys = sorted(int(k.replace("Q", "")) for k in q_returns.keys())
    vals = [q_returns.get(f"Q{q}", 0) for q in keys]
    reversals = (sum(1 for i in range(len(vals) - 1) if vals[i] < vals[i + 1])
                 if direction == "negative" else
                 sum(1 for i in range(len(vals) - 1) if vals[i] > vals[i + 1]))
    monotonic = reversals <= 1

    passed = (ic_abs_mean >= 0.008 and icir_annual >= 0.5 and
              directional_win >= 0.52 and monotonic)
    return {"passed": passed, "ic_raw_mean": round(ic_raw_mean, 4),
            "ic_abs_mean": round(ic_abs_mean, 4), "direction": direction,
            "icir_annual": round(icir_annual, 4), "ic_std": round(ic_std, 4),
            "directional_win": round(directional_win, 4),
            "monotonic": monotonic, "quantile_returns": q_returns}


# ═══════════════════════════════════════════════════════════════
# S1 — 月度IC稳定性
# ═══════════════════════════════════════════════════════════════

def monthly_ic_stability(df, factor_col="factor_value", return_col="future_ret_5d"):
    """S1: 月度IC是否持续显著。

    将每日IC按月汇总。检查：(1) 正IC月份占比，(2) 月度ICIR，(3) 趋势。
    """
    ic_df = compute_daily_ic(df, factor_col, return_col)
    ic_df["month"] = ic_df["date"].dt.to_period("M")
    monthly = ic_df.groupby("month")["ic"].mean().dropna()

    if len(monthly) < 12:
        return {"error": f"只有 {len(monthly)} 个月"}

    monthly_vals = monthly.values
    monthly_icir = float(np.mean(monthly_vals) / np.std(monthly_vals)) if np.std(monthly_vals) > 0 else 0
    pos_ratio = float((monthly_vals > 0).mean())

    # 趋势检测：月度IC是否在衰减
    slope, _, _, pvalue, _ = linregress(range(len(monthly_vals)), monthly_vals)
    declining = slope < 0 and pvalue < 0.05

    # 月度IC稳定性：要求大多数月份方向一致
    direction = monthly_vals.mean() > 0
    consistent = max((monthly_vals > 0).mean(), (monthly_vals < 0).mean()) >= 0.55

    passed = abs(monthly_icir) >= 0.3 and consistent and not declining

    return {"passed": passed, "n_months": len(monthly_vals),
            "monthly_icir": round(monthly_icir, 4),
            "positive_month_ratio": round(pos_ratio, 4),
            "consistent_ratio": round(max(pos_ratio, 1 - pos_ratio), 4),
            "consistency_ok": consistent,
            "trend_slope": round(float(slope) * 252, 6),
            "trend_pvalue": round(float(pvalue), 4),
            "declining": declining}


# ═══════════════════════════════════════════════════════════════
# S2 — CSCV/PBO
# ═══════════════════════════════════════════════════════════════

def cscv_pbo(df, factor_col="factor_value", return_col="future_ret_5d",
             n_splits=16, n_trials=500):
    """S2: IC方向在时间切片上的稳定性 (Lopez de Prado 2014)"""
    ic_df = compute_daily_ic(df, factor_col, return_col)
    ic_vals = ic_df["ic"].values
    if len(ic_vals) < n_splits * 20: return {"error": f"数据不足"}

    chunk_size = len(ic_vals) // n_splits
    chunks = [ic_vals[i * chunk_size:(i + 1) * chunk_size] for i in range(n_splits)]
    n_is = n_splits // 2

    oos_ranks = {0: [], 1: []}
    rng = np.random.RandomState(42)

    for _ in range(min(n_trials, 1000)):
        indices = np.arange(n_splits); rng.shuffle(indices)
        is_ic = np.concatenate([chunks[i] for i in indices[:n_is]])
        oos_ic = np.concatenate([chunks[i] for i in indices[n_is:]])
        is_perf = {0: np.mean(is_ic), 1: -np.mean(is_ic)}
        is_best = max(is_perf, key=is_perf.get)
        oos_mean = np.mean(oos_ic)
        oos_sorted = sorted({0: oos_mean, 1: -oos_mean}.items(), key=lambda x: x[1], reverse=True)
        rank_map = {sid: rank for rank, (sid, _) in enumerate(oos_sorted)}
        oos_ranks[is_best].append(rank_map[is_best])

    all_ranks = [r for ranks in oos_ranks.values() for r in ranks]
    if not all_ranks: return {"error": "CSCV计算失败"}

    pbo = float(sum(1 for r in all_ranks if r > 0) / len(all_ranks))
    return {"pbo": round(pbo, 4), "pbo_passed": pbo <= 0.5,
            "n_trials": len(all_ranks),
            "note": "单因子CSCV测IC方向稳定性（正/反），非参数遍历。"}


# ═══════════════════════════════════════════════════════════════
# S3 — IC衰减建模
# ═══════════════════════════════════════════════════════════════

def alpha_decay_fit(df, factor_col="factor_value", return_col="future_ret_5d", window_days=252):
    """S3: 三模型拟合IC衰减 (Lee 2025)"""
    ic_df = compute_daily_ic(df, factor_col, return_col)
    ic_vals = ic_df["ic"].dropna().values
    if len(ic_vals) < window_days * 2: return {"error": "IC序列太短"}

    rolling_ic = pd.Series(np.abs(ic_vals)).rolling(window_days).mean().dropna().values
    t = np.arange(len(rolling_ic))

    from scipy.optimize import curve_fit
    models = {}
    for name, fn, p0 in [
        ("linear", lambda x, a, b: a + b * x, [rolling_ic[0], -0.0001]),
        ("exponential", lambda x, a, l: a * np.exp(-l * x), [rolling_ic[0], 0.001]),
        ("hyperbolic", lambda x, K, l: K / (1 + l * x), [rolling_ic[0], 0.001]),
    ]:
        try:
            p, _ = curve_fit(fn, t, rolling_ic, p0=p0, maxfev=5000)
            pred = fn(t, *p)
            r2 = 1 - np.sum((rolling_ic - pred) ** 2) / (np.sum((rolling_ic - rolling_ic.mean()) ** 2) + 1e-12)
            hl = (-int(p[0] / (2 * p[1])) if name == "linear" and p[1] < 0
                  else int(1.0 / p[1]) if name == "hyperbolic" and p[1] > 0
                  else int(np.log(2) / p[1]) if name == "exponential" and p[1] > 0 else -1)
            models[name] = {"r2": round(max(r2, 0), 4), "half_life": hl}
        except Exception:
            models[name] = {"error": "拟合失败"}

    best = max(models, key=lambda n: models[n].get("r2", -1))
    hl = models[best].get("half_life", -1)
    severity = ("severe" if 0 < hl < 252 else "moderate" if 0 < hl < 756
                else "mild" if hl > 0 else "no_decay_or_error")

    return {"models": models, "best_model": best,
            "best_r2": models[best].get("r2", 0),
            "half_life_trading_days": hl,
            "half_life_years": round(hl / 252, 2) if hl > 0 else -1,
            "decay_severity": severity}


# ═══════════════════════════════════════════════════════════════
# S4 — 分位价差稳定性
# ═══════════════════════════════════════════════════════════════

def quantile_spread_stability(df, factor_col="factor_value", return_col="future_ret_5d",
                              n_quantiles=5):
    """S4: 截面多空价差是否持续存在。

    每天按因子值分5组，计算极端组(Q0和Q4)的收益差。
    方向由S0确定：IC为负时 Q0-Q4(反转因子)，IC为正时 Q4-Q0(趋势因子)。
    """
    s0 = quick_filter(df, factor_col, return_col)
    direction = s0.get("direction", "negative")

    data = df[[factor_col, return_col, "date"]].dropna().copy()
    data["month"] = data["date"].dt.to_period("M")

    # 每日价差
    daily_spreads = []
    for dt, g in data.groupby("date"):
        if len(g) < n_quantiles * 5: continue
        g["q"] = pd.qcut(g[factor_col], n_quantiles, labels=False, duplicates="drop")
        q0_ret = g[g["q"] == 0][return_col].mean()
        q4_ret = g[g["q"] == n_quantiles - 1][return_col].mean()
        if direction == "negative":
            spread = q0_ret - q4_ret  # 反转：低因子值涨得多
        else:
            spread = q4_ret - q0_ret  # 趋势：高因子值涨得多
        daily_spreads.append(spread)

    if len(daily_spreads) < 60: return {"error": "数据不足"}

    spreads = np.array(daily_spreads)
    spread_mean = float(np.mean(spreads))
    spread_tstat = float(spread_mean / (np.std(spreads) / np.sqrt(len(spreads)))) if np.std(spreads) > 0 else 0
    direction_match = float((spreads > 0).mean())

    # 月度价差稳定性
    monthly_spreads = data.groupby("month").apply(
        lambda g: _monthly_spread(g, factor_col, return_col, n_quantiles, direction)
    ).dropna()
    monthly_pos_ratio = float((monthly_spreads > 0).mean()) if len(monthly_spreads) > 0 else 0

    passed = spread_tstat > 2.0

    return {"passed": passed,
            "daily_spread_mean": round(spread_mean, 6),
            "daily_spread_tstat": round(spread_tstat, 4),
            "daily_direction_match": round(direction_match, 4),
            "monthly_positive_ratio": round(monthly_pos_ratio, 4),
            "n_daily_spreads": len(daily_spreads),
            "n_monthly": len(monthly_spreads) if len(monthly_spreads) > 0 else 0}


def _monthly_spread(g, factor_col, return_col, n_quantiles, direction):
    g = g.copy()
    if len(g) < n_quantiles * 5: return None
    g["q"] = pd.qcut(g[factor_col], n_quantiles, labels=False, duplicates="drop")
    q0_r = g[g["q"] == 0][return_col].mean()
    q4_r = g[g["q"] == n_quantiles - 1][return_col].mean()
    return q0_r - q4_r if direction == "negative" else q4_r - q0_r


# ═══════════════════════════════════════════════════════════════
# 主流水线
# ═══════════════════════════════════════════════════════════════

def run_validation(df, factor_col="factor_value", return_col="future_ret_5d"):
    report = {"factor_column": factor_col}

    report["S0_quick_filter"] = quick_filter(df, factor_col, return_col)
    report["S1_monthly_ic"] = monthly_ic_stability(df, factor_col, return_col)
    report["S2_cscv_pbo"] = cscv_pbo(df, factor_col, return_col)
    report["S3_alpha_decay"] = alpha_decay_fit(df, factor_col, return_col)
    report["S4_quantile_spread"] = quantile_spread_stability(df, factor_col, return_col)

    report["verdict"] = _verdict(report)
    return report


def _verdict(report):
    issues = []
    if not report.get("S0_quick_filter", {}).get("passed"): issues.append("S0")
    s1 = report.get("S1_monthly_ic", {})
    if not s1.get("passed"): issues.append("S1")
    s2 = report.get("S2_cscv_pbo", {})
    if s2.get("pbo", 1) is not None and s2.get("pbo", 1) > 0.5: issues.append("S2")
    s3 = report.get("S3_alpha_decay", {})
    if s3.get("decay_severity") == "severe": issues.append("S3")
    if not report.get("S4_quantile_spread", {}).get("passed"): issues.append("S4")
    return "PASS" if not issues else f"WARNING ({len(issues)}): {', '.join(issues)}"
