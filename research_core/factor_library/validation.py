# ============================================================
# Factor Validation - 因子验证模块
# ============================================================

import numpy as np
import pandas as pd


def compute_forward_returns(
    df: pd.DataFrame,
    price_col: str = "close",
    periods: int = 20,
    date_col: str = "date",
    code_col: str = "code",
) -> pd.DataFrame:
    """Compute forward returns by security using ``periods`` rows ahead."""
    data = df.sort_values([code_col, date_col]).copy()
    future_price = data.groupby(code_col)[price_col].shift(-periods)
    data["forward_return"] = future_price / data[price_col] - 1
    return data[[date_col, code_col, "forward_return"]]


def compute_ic(factor_values, returns):
    """
    计算截面IC

    参数:
        factor_values: Series, 因子值
        returns: Series, 同期收益率

    返回:
        float, IC值
    """
    valid_idx = factor_values.notna() & returns.notna()
    if valid_idx.sum() < 2:
        return np.nan
    return factor_values[valid_idx].corr(returns[valid_idx], method="spearman")


def compute_ic_series(
    factor_df: pd.DataFrame,
    return_df: pd.DataFrame,
    factors: list[str],
    date_col: str = "date",
    code_col: str = "code",
    return_col: str = "forward_return",
) -> pd.DataFrame:
    """Compute cross-sectional Spearman IC for each date and factor."""
    merged = pd.merge(factor_df, return_df, on=[date_col, code_col], how="inner")
    rows = []
    for date, group in merged.groupby(date_col):
        for factor in factors:
            valid = group[[factor, return_col]].dropna()
            rows.append({
                date_col: date,
                "factor": factor,
                "ic": valid[factor].corr(valid[return_col], method="spearman") if len(valid) >= 2 else np.nan,
                "n": len(valid),
            })
    return pd.DataFrame(rows)


def compute_monthly_ic(
    factor_df,
    returns_df,
    date_col="date",
    code_col="code",
    return_col="forward_return",
):
    """
    计算月频IC序列

    参数:
        factor_df: DataFrame, 因子值 [date, code, alpha...]
        returns_df: DataFrame, forward returns [date, code, forward_return]

    返回:
        DataFrame, IC时间序列
    """
    if return_col not in returns_df.columns:
        raise KeyError(
            f"returns_df must contain '{return_col}'. "
            "Use compute_forward_returns() output or pass return_col explicitly."
        )

    merged = pd.merge(factor_df, returns_df, on=[date_col, code_col], how='inner')
    alpha_cols = [c for c in factor_df.columns if c not in [date_col, code_col]]

    ic_results = []
    for date in merged[date_col].unique():
        day_data = merged[merged[date_col] == date]
        day_ic = {}
        day_ic[date_col] = date
        for alpha_col in alpha_cols:
            day_ic[alpha_col] = compute_ic(day_data[alpha_col], day_data[return_col])
        ic_results.append(day_ic)

    return pd.DataFrame(ic_results)


def summarize_ic(ic_df, date_col='date'):
    """
    汇总IC统计指标

    参数:
        ic_df: DataFrame, IC时间序列

    返回:
        DataFrame, IC统计摘要
    """
    if {"factor", "ic"}.issubset(ic_df.columns):
        summary = []
        for factor, group in ic_df.groupby("factor"):
            ic_series = group["ic"].dropna()
            summary.append({
                "factor": factor,
                "mean_ic": ic_series.mean(),
                "std_ic": ic_series.std(),
                "ic_ir": ic_series.mean() / ic_series.std() if ic_series.std() > 0 else np.nan,
                "win_rate": (ic_series > 0).mean(),
                "n_periods": len(ic_series),
                "mean_n": group["n"].mean() if "n" in group else np.nan,
            })
        return pd.DataFrame(summary)

    alpha_cols = [c for c in ic_df.columns if c != date_col]
    summary = []

    for alpha_col in alpha_cols:
        ic_series = ic_df[alpha_col].dropna()
        summary.append({
            'factor': alpha_col,
            'mean_ic': ic_series.mean(),
            'std_ic': ic_series.std(),
            'ic_ir': ic_series.mean() / ic_series.std() if ic_series.std() > 0 else np.nan,
            'win_rate': (ic_series > 0).mean(),
            'n_periods': len(ic_series)
        })

    return pd.DataFrame(summary)
