from __future__ import annotations

import numpy as np
import pandas as pd


def _finite_values(values: list[float]) -> list[float]:
    return [float(value) for value in values if pd.notna(value)]


def _mean_or_nan(values: list[float]) -> float:
    cleaned = _finite_values(values)
    return float(np.mean(cleaned)) if cleaned else float("nan")


def _std_or_nan(values: list[float]) -> float:
    cleaned = _finite_values(values)
    if len(cleaned) < 2:
        return float("nan")
    return float(np.std(cleaned, ddof=1))


def _t_stat(values: list[float]) -> float:
    cleaned = _finite_values(values)
    if len(cleaned) < 2:
        return float("nan")
    mean = float(np.mean(cleaned))
    std = float(np.std(cleaned, ddof=1))
    if std == 0:
        return float("nan")
    return float(mean / (std / np.sqrt(len(cleaned))))


def _win_rate(values: list[float]) -> float:
    cleaned = _finite_values(values)
    if not cleaned:
        return float("nan")
    return float(sum(1 for value in cleaned if value > 0) / len(cleaned))


def _test_monotonicity(group_means: list[float]) -> dict:
    valid = [value for value in group_means if pd.notna(value)]
    if len(valid) < 2:
        return {"is_strict": False, "ratio": float("nan"), "direction": "unknown", "group_means": group_means}
    increasing = sum(1 for index in range(len(valid) - 1) if valid[index + 1] > valid[index])
    decreasing = sum(1 for index in range(len(valid) - 1) if valid[index + 1] < valid[index])
    pairs = len(valid) - 1
    direction = "increasing" if increasing >= decreasing else "decreasing"
    ratio = (increasing if increasing >= decreasing else decreasing) / pairs if pairs else 0.0
    return {"is_strict": ratio == 1.0, "ratio": float(ratio), "direction": direction, "group_means": group_means}


def _empty_result(factor_name: str, n_groups: int) -> dict:
    return {
        "factor_name": factor_name,
        "n_groups": n_groups,
        "dataset": {"n_stocks": 0, "n_dates": 0, "n_cross_sections": 0},
        "group_returns": {},
        "long_short": {"mean": float("nan"), "std": float("nan"), "t_stat": float("nan"), "win_rate": float("nan"), "n_obs": 0},
        "monotonicity": {"is_strict": False, "ratio": float("nan"), "direction": "unknown", "group_means": []},
        "metrics": {},
        "ic_summary": {},
        "group_nav": {"dates": [], "cumulative": {}},
        "daily_series": [],
    }


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
    price_panel = panel[[date_col, code_col, price_col]].copy()
    price_panel = price_panel.sort_values([code_col, date_col]).reset_index(drop=True)
    price_panel["_fwd_ret"] = (
        price_panel.groupby(code_col)[price_col].shift(-forward_periods) / price_panel[price_col] - 1
    )
    enriched = factor_frame.merge(
        price_panel[[date_col, code_col, "_fwd_ret"]],
        on=[date_col, code_col],
        how="left",
    )
    valid = enriched.dropna(subset=[factor_name, "_fwd_ret"])
    if valid.empty:
        return _empty_result(factor_name, n_groups)

    group_labels = list(range(1, n_groups + 1))
    group_return_series: dict[int, list[float]] = {group: [] for group in group_labels}
    long_short_series: list[float] = []
    rank_ic_series: list[float] = []
    pearson_ic_series: list[float] = []
    daily_records: list[dict] = []
    nav_records: list[dict] = []

    for date_value, day in valid.groupby(date_col):
        if len(day) < max(n_groups * 2, 4):
            continue
        day = day.copy()
        day["_rank_pct"] = day[factor_name].rank(method="average", pct=True)
        day["_group"] = np.ceil(day["_rank_pct"] * n_groups).clip(1, n_groups).astype(int)
        actual_groups = sorted(day["_group"].unique())
        if len(actual_groups) < 2:
            continue

        group_returns = day.groupby("_group")["_fwd_ret"].mean()
        for group in group_labels:
            group_return_series[group].append(float(group_returns.get(group, np.nan)))

        bottom_group = actual_groups[0]
        top_group = actual_groups[-1]
        top_return = group_returns.get(top_group, np.nan)
        bottom_return = group_returns.get(bottom_group, np.nan)
        long_short = float(top_return - bottom_return) if pd.notna(top_return) and pd.notna(bottom_return) else None
        if long_short is not None:
            long_short_series.append(long_short)

        factor_values = day[factor_name]
        forward_returns = day["_fwd_ret"]
        pearson_ic = factor_values.corr(forward_returns)
        rank_ic = factor_values.rank().corr(forward_returns.rank())
        pearson_ic_series.append(float(pearson_ic))
        rank_ic_series.append(float(rank_ic))

        daily_records.append(
            {
                "date": pd.Timestamp(date_value).strftime("%Y-%m-%d"),
                "n_stocks": int(len(day)),
                "groups": {str(group): float(group_returns.get(group, np.nan)) for group in group_labels},
                "long_short": long_short,
                "rank_ic": float(rank_ic),
                "ic": float(pearson_ic),
            }
        )
        nav_entry: dict = {"date": pd.Timestamp(date_value).strftime("%Y-%m-%d")}
        for group in group_labels:
            nav_entry[f"g{group}"] = float(group_returns.get(group, np.nan))
        nav_records.append(nav_entry)

    group_stats: dict[str, dict] = {}
    for group in group_labels:
        values = [value for value in group_return_series[group] if pd.notna(value)]
        mean_value = _mean_or_nan(values)
        group_stats[str(group)] = {
            "mean": mean_value,
            "std": _std_or_nan(values),
            "annual_return": float(mean_value * 252) if pd.notna(mean_value) else float("nan"),
            "t_stat": _t_stat(values),
            "win_rate": _win_rate(values),
            "n_obs": len(values),
        }

    long_short_mean = _mean_or_nan(long_short_series)
    long_short_std = _std_or_nan(long_short_series)
    rank_ic_mean = _mean_or_nan(rank_ic_series)
    rank_ic_std = _std_or_nan(rank_ic_series)
    pearson_ic_mean = _mean_or_nan(pearson_ic_series)
    pearson_ic_std = _std_or_nan(pearson_ic_series)

    nav_frame = pd.DataFrame(nav_records)
    group_nav: dict = {"dates": [], "cumulative": {}}
    if not nav_frame.empty and "date" in nav_frame.columns:
        nav_frame = nav_frame.sort_values("date").reset_index(drop=True)
        group_nav["dates"] = nav_frame["date"].tolist()
        for group in group_labels:
            running = 1.0
            cumulative: list[float] = []
            for value in nav_frame[f"g{group}"]:
                if pd.notna(value):
                    running *= 1.0 + float(value)
                cumulative.append(float(running))
            group_nav["cumulative"][str(group)] = cumulative

    return {
        "factor_name": factor_name,
        "n_groups": n_groups,
        "description": {
            "universe": f"{int(panel[code_col].nunique())} stocks",
            "rebalance_frequency": "daily",
            "holding_period": f"T+{forward_periods}",
            "grouping_method": "daily cross-sectional quantile grouping by factor value",
            "group_labels": {
                str(group): f"{int((group - 1) / n_groups * 100)}%-{int(group / n_groups * 100)}% factor quantile"
                for group in group_labels
            },
        },
        "dataset": {
            "n_stocks": int(panel[code_col].nunique()),
            "n_dates": int(panel[date_col].nunique()),
            "n_cross_sections": len(daily_records),
        },
        "group_returns": group_stats,
        "long_short": {
            "mean": long_short_mean,
            "std": long_short_std,
            "t_stat": _t_stat(long_short_series),
            "win_rate": _win_rate(long_short_series),
            "n_obs": len(long_short_series),
        },
        "monotonicity": _test_monotonicity([group_stats[str(group)]["mean"] for group in group_labels]),
        "metrics": {
            "rank_ic_mean": rank_ic_mean,
            "rank_ic_ir": float(rank_ic_mean / rank_ic_std) if pd.notna(rank_ic_mean) and pd.notna(rank_ic_std) and rank_ic_std != 0 else float("nan"),
            "long_short_sharpe": float(long_short_mean / long_short_std * np.sqrt(252)) if pd.notna(long_short_mean) and pd.notna(long_short_std) and long_short_std != 0 else float("nan"),
            "long_short_annual_return": float(long_short_mean * 252) if pd.notna(long_short_mean) else float("nan"),
        },
        "ic_summary": {
            "rank_ic_mean": rank_ic_mean,
            "rank_ic_std": rank_ic_std,
            "rank_ic_ir": float(rank_ic_mean / rank_ic_std) if pd.notna(rank_ic_mean) and pd.notna(rank_ic_std) and rank_ic_std != 0 else float("nan"),
            "rank_ic_win_rate": _win_rate(rank_ic_series),
            "pearson_ic_mean": pearson_ic_mean,
            "pearson_ic_std": pearson_ic_std,
            "pearson_ic_ir": float(pearson_ic_mean / pearson_ic_std) if pd.notna(pearson_ic_mean) and pd.notna(pearson_ic_std) and pearson_ic_std != 0 else float("nan"),
            "n_obs": len(rank_ic_series),
        },
        "group_nav": group_nav,
        "daily_series": daily_records,
    }
