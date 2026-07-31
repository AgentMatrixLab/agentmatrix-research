"""Universal single-factor stratified analysis engine.

Provides a factor-set-agnostic analysis pipeline: given any factor value
frame (date x code x factor_value) and the corresponding market panel,
it computes quantile-group returns, cumulative NAV, long-short spreads,
IC statistics, and monotonicity tests.

Works identically for Alpha101, GTJA191, WQ101, or any custom factor.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _mean_or_nan(values: list[float]) -> float:
    cleaned = [float(v) for v in values if pd.notna(v)]
    return float(np.mean(cleaned)) if cleaned else float("nan")


def _std_or_nan(values: list[float]) -> float:
    cleaned = [float(v) for v in values if pd.notna(v)]
    if len(cleaned) < 2:
        return float("nan")
    return float(np.std(cleaned, ddof=1))


def compute_stratified_analysis(
    panel: pd.DataFrame,
    factor_frame: pd.DataFrame,
    *,
    factor_name: str,
    n_groups: int = 10,
    forward_periods: int = 1,
    price_col: str = "close",
    date_col: str = "date",
    code_col: str = "code",
) -> dict:
    enriched = factor_frame.merge(
        panel[[date_col, code_col, price_col]],
        on=[date_col, code_col], how="left",
    )
    price_panel = (
        panel[[date_col, code_col, price_col]]
        .sort_values([code_col, date_col]).reset_index(drop=True)
    )
    enriched["_fwd_ret"] = _compute_forward_returns(
        price_panel, price_col=price_col, code_col=code_col, periods=forward_periods,
    )
    valid = enriched.dropna(subset=[factor_name, "_fwd_ret"])
    if valid.empty:
        return _empty_result(factor_name, n_groups)

    n_cross = 0
    group_labels = list(range(1, n_groups + 1))
    group_ret_series: dict[int, list[float]] = {g: [] for g in group_labels}
    long_short_series: list[float] = []
    rank_ic_series: list[float] = []
    pearson_ic_series: list[float] = []
    daily_records: list[dict] = []
    nav_records: list[dict] = []

    for date_val, day in valid.groupby(date_col):
        if len(day) < n_groups * 2:
            continue
        day = day.copy()
        day["_pct"] = day[factor_name].rank(method="average", pct=True)
        day["_group"] = np.ceil(day["_pct"] * n_groups).clip(1, n_groups).astype(int)
        actual_groups = sorted(day["_group"].unique())
        if len(actual_groups) < 2:
            continue

        grp_ret = day.groupby("_group")["_fwd_ret"].mean()
        for g in group_labels:
            group_ret_series[g].append(float(grp_ret.get(g, np.nan)))

        top_g, bot_g = actual_groups[-1], actual_groups[0]
        top_ret = grp_ret.get(top_g, np.nan)
        bot_ret = grp_ret.get(bot_g, np.nan)
        if pd.notna(top_ret) and pd.notna(bot_ret):
            long_short_series.append(float(top_ret - bot_ret))

        fv = day[factor_name]
        fr = day["_fwd_ret"]
        pearson_ic_series.append(float(fv.corr(fr)))
        rank_ic_series.append(float(fv.rank().corr(fr.rank())))

        daily_records.append({
            "date": str(date_val), "n_stocks": int(len(day)),
            "groups": {str(g): float(grp_ret.get(g, np.nan)) for g in group_labels},
            "long_short": float(top_ret - bot_ret) if pd.notna(top_ret) and pd.notna(bot_ret) else None,
            "rank_ic": rank_ic_series[-1],
        })
        entry: dict = {"date": str(date_val)}
        for g in group_labels:
            entry[f"g{g}"] = float(grp_ret.get(g, np.nan))
        nav_records.append(entry)
        n_cross += 1

    group_stats: dict[str, dict] = {}
    for g in group_labels:
        vals = [v for v in group_ret_series[g] if pd.notna(v)]
        mean_val = _mean_or_nan(vals)
        group_stats[str(g)] = {
            "mean": mean_val, "std": _std_or_nan(vals),
            "annual_return": float(mean_val * 252) if pd.notna(mean_val) else float("nan"),
            "t_stat": _t_stat(vals), "win_rate": _win_rate(vals), "n_obs": len(vals),
        }

    ls_mean = _mean_or_nan(long_short_series)
    ls_std = _std_or_nan(long_short_series)
    long_short = {"mean": ls_mean, "std": ls_std, "t_stat": _t_stat(long_short_series),
                  "win_rate": _win_rate(long_short_series), "n_obs": len(long_short_series)}

    gmeans = [group_stats[str(g)]["mean"] for g in group_labels]
    monotonicity = _test_monotonicity(gmeans)

    ric_mean = _mean_or_nan(rank_ic_series)
    ric_std = _std_or_nan(rank_ic_series)
    pic_mean = _mean_or_nan(pearson_ic_series)
    pic_std = _std_or_nan(pearson_ic_series)
    ic_summary = {
        "rank_ic_mean": ric_mean, "rank_ic_std": ric_std,
        "rank_ic_ir": float(ric_mean / ric_std) if pd.notna(ric_mean) and pd.notna(ric_std) and ric_std != 0 else float("nan"),
        "rank_ic_win_rate": _win_rate(rank_ic_series),
        "pearson_ic_mean": pic_mean, "pearson_ic_std": pic_std,
        "pearson_ic_ir": float(pic_mean / pic_std) if pd.notna(pic_mean) and pd.notna(pic_std) and pic_std != 0 else float("nan"),
        "n_obs": len(rank_ic_series),
    }

    nav_df = pd.DataFrame(nav_records)
    group_nav: dict = {"dates": [], "cumulative": {}}
    if not nav_df.empty and "date" in nav_df.columns:
        nav_df = nav_df.sort_values("date").reset_index(drop=True)
        group_nav["dates"] = nav_df["date"].tolist()
        for g in group_labels:
            col = f"g{g}"
            cum = []; running = 1.0
            for v in nav_df[col]:
                if pd.notna(v): running *= (1.0 + v)
                cum.append(running)
            group_nav["cumulative"][str(g)] = cum

    return {
        "factor_name": factor_name, "n_groups": n_groups,
        "description": {
            "universe": f"{int(panel[code_col].nunique())} stocks",
            "rebalance_frequency": "日频（每日调仓）",
            "holding_period": f"T+{forward_periods}",
            "grouping_method": "每日横截面按因子值排序 → 等分位分组",
            "group_labels": {str(g): f"最低{int((g-1)/n_groups*100)}%-{int(g/n_groups*100)}%因子值" for g in group_labels},
        },
        "dataset": {"n_stocks": int(panel[code_col].nunique()),
                     "n_dates": int(panel[date_col].nunique()), "n_cross_sections": n_cross},
        "group_returns": group_stats, "long_short": long_short,
        "monotonicity": monotonicity,
        "metrics": {
            "rank_ic_mean": ric_mean, "rank_ic_ir": float(ric_mean / ric_std) if pd.notna(ric_mean) and pd.notna(ric_std) and ric_std != 0 else float("nan"),
            "long_short_sharpe": float(ls_mean / ls_std * np.sqrt(252)) if pd.notna(ls_mean) and pd.notna(ls_std) and ls_std != 0 else float("nan"),
            "long_short_annual_return": float(ls_mean * 252) if pd.notna(ls_mean) else float("nan"),
        },
        "ic_summary": ic_summary,
        "group_nav": group_nav, "daily_series": daily_records,
    }


def batch_stratified_analysis(
    panel, factor_frame, *, factor_names: list[str], n_groups=10, forward_periods=1,
    price_col="close", date_col="date", code_col="code",
) -> dict[str, dict]:
    return {
        fn: compute_stratified_analysis(panel, factor_frame, factor_name=fn,
            n_groups=n_groups, forward_periods=forward_periods,
            price_col=price_col, date_col=date_col, code_col=code_col)
        for fn in factor_names
    }


def _compute_forward_returns(panel, *, price_col="close", code_col="code", periods=1):
    future = panel.groupby(code_col)[price_col].shift(-periods)
    return future / panel[price_col] - 1


def _t_stat(values):
    cleaned = [float(v) for v in values if pd.notna(v)]
    if len(cleaned) < 2: return float("nan")
    m = np.mean(cleaned); s = np.std(cleaned, ddof=1)
    if s == 0: return float("nan")
    return float(m / (s / np.sqrt(len(cleaned))))


def _win_rate(values):
    cleaned = [v for v in values if pd.notna(v)]
    if not cleaned: return float("nan")
    return float(sum(1 for v in cleaned if v > 0) / len(cleaned))


def _test_monotonicity(group_means):
    valid = [m for m in group_means if pd.notna(m)]
    if len(valid) < 2:
        return {"is_strict": False, "ratio": float("nan"), "direction": "unknown", "group_means": group_means}
    inc = sum(1 for i in range(len(valid)-1) if valid[i+1] > valid[i])
    dec = sum(1 for i in range(len(valid)-1) if valid[i+1] < valid[i])
    pairs = len(valid) - 1
    direction = "increasing" if inc >= dec else "decreasing"
    ratio = (inc if inc >= dec else dec) / pairs if pairs else 0.0
    return {"is_strict": ratio == 1.0, "ratio": ratio, "direction": direction, "group_means": group_means}


def _empty_result(factor_name, n_groups):
    return {
        "factor_name": factor_name, "n_groups": n_groups,
        "dataset": {"n_stocks": 0, "n_dates": 0, "n_cross_sections": 0},
        "group_returns": {}, "long_short": {"mean": float("nan"), "std": float("nan"),
            "t_stat": float("nan"), "win_rate": float("nan"), "n_obs": 0},
        "monotonicity": {"is_strict": False, "ratio": float("nan"), "direction": "unknown", "group_means": []},
        "ic_summary": {}, "group_nav": {"dates": [], "cumulative": {}}, "daily_series": [],
    }