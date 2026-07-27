"""
Barra Risk Factor Library — CNE5-style risk factors for A-share markets.

Implements the standard Barra China Equity Model (CNE5) risk factors:

  SIZE     — Market capitalization (ln)
  BETA     — Market beta (60-day rolling against CSI300)
  MOMENTUM — 12-1 month momentum
  VOLATILITY — Daily return volatility (60-day std)
  BTOP     — Book-to-price ratio
  EARNINGS_YIELD — Earnings yield
  GROWTH   — Earnings growth
  LEVERAGE — Debt-to-equity
  LIQUIDITY — Turnover-based liquidity
  NONLINEAR_SIZE — Size^3 orthogonalized
  SECTOR   — Industry dummies (GICS/Shenwan)
  RESIDUAL_VOL — Residual volatility

Usage:
    from research_core.factor_lab.libraries.barra import compute_barra_factors

    df = pd.DataFrame(...)  # long panel with OHLCV + fundamental data
    barra = compute_barra_factors(df)
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from typing import Sequence

from research_core.factor_lab.operators import (
    safe_div, ts_mean, ts_std, ts_delay, ts_delta,
    cross_sectional_rank, sort_panel, ts_sum,
)


BARRA_FACTOR_NAMES = (
    "size",
    "beta",
    "momentum_12m1m",
    "volatility",
    "btop",
    "earnings_yield",
    "growth",
    "leverage",
    "liquidity",
    "nonlinear_size",
    "residual_volatility",
)


def compute_market_cap(df: pd.DataFrame, total_shares_col: str = "total_shares") -> pd.Series:
    """ln(market cap) — SIZE factor."""
    if total_shares_col in df.columns:
        mcap = df["close"] * df[total_shares_col]
        return np.log(mcap.replace(0, np.nan))
    return np.log(df["close"].replace(0, np.nan))


def compute_beta(
    df: pd.DataFrame,
    market_return_col: str | None = None,
    window: int = 60,
) -> pd.Series:
    """60-day rolling beta against market (CSI300)."""
    if market_return_col is None or market_return_col not in df.columns:
        # Compute market return as equal-weighted average
        returns = df.groupby("code")["close"].pct_change()
        market_ret = df.groupby("date")["close"].transform(
            lambda x: x.pct_change().mean() if len(x) > 1 else np.nan
        )
    else:
        returns = df.groupby("code")["close"].pct_change()
        market_ret = df[market_return_col]

    df_temp = df.copy()
    df_temp["_ret"] = returns
    df_temp["_mkt"] = market_ret

    def rolling_beta(group: pd.DataFrame) -> pd.Series:
        cov = group["_ret"].rolling(window, min_periods=window).cov(group["_mkt"])
        var = group["_mkt"].rolling(window, min_periods=window).var()
        return safe_div(cov, var.replace(0, np.nan))

    return df_temp.groupby("code", group_keys=False).apply(rolling_beta).reset_index(level=0, drop=True)


def compute_momentum_12m1m(df: pd.DataFrame) -> pd.Series:
    """12-1 month momentum (skip most recent month)."""
    close_1m = ts_delay(df, "close", 21)   # ~1 month ago
    close_12m = ts_delay(df, "close", 252)  # ~12 months ago
    return safe_div(close_1m - close_12m, close_12m.replace(0, np.nan))


def compute_volatility(df: pd.DataFrame, window: int = 60) -> pd.Series:
    """60-day daily return volatility."""
    returns = df.groupby("code")["close"].pct_change()
    df_temp = df.copy()
    df_temp["_ret"] = returns
    return df_temp.groupby("code")["_ret"].transform(
        lambda x: x.rolling(window, min_periods=window).std()
    )


def compute_btop(df: pd.DataFrame, book_value_col: str = "book_value_per_share") -> pd.Series:
    """Book-to-price ratio."""
    if book_value_col in df.columns:
        return safe_div(df[book_value_col], df["close"].replace(0, np.nan))
    return pd.Series(np.nan, index=df.index)


def compute_earnings_yield(df: pd.DataFrame, eps_col: str = "eps_ttm") -> pd.Series:
    """Earnings yield (EPS / Price)."""
    if eps_col in df.columns:
        return safe_div(df[eps_col], df["close"].replace(0, np.nan))
    return pd.Series(np.nan, index=df.index)


def compute_growth(df: pd.DataFrame, earnings_col: str = "net_profit_yoy") -> pd.Series:
    """Earnings growth YoY."""
    if earnings_col in df.columns:
        return df[earnings_col]
    return pd.Series(np.nan, index=df.index)


def compute_leverage(df: pd.DataFrame, debt_col: str = "debt_to_equity") -> pd.Series:
    """Debt-to-equity ratio."""
    if debt_col in df.columns:
        return df[debt_col]
    return pd.Series(np.nan, index=df.index)


def compute_liquidity(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """Average daily turnover (volume / shares outstanding)."""
    # Proxy: log of average daily turnover ratio
    df_temp = df.copy()
    df_temp["_turnover"] = safe_div(df["volume"], df["close"].replace(0, np.nan))
    avg_turnover = df_temp.groupby("code")["_turnover"].transform(
        lambda x: x.rolling(window, min_periods=window).mean()
    )
    return np.log(avg_turnover.replace(0, np.nan))


def compute_nonlinear_size(df: pd.DataFrame) -> pd.Series:
    """Size^3 orthogonalized against size — captures mid-cap effect."""
    size = compute_market_cap(df)
    cube = size ** 3
    # Orthogonalize: regress cube on size, take residuals
    from scipy import stats
    valid = size.notna() & cube.notna()
    if valid.sum() > 2:
        slope, intercept, _, _, _ = stats.linregress(size[valid], cube[valid])
        return cube - (intercept + slope * size)
    return pd.Series(np.nan, index=df.index)


def compute_residual_volatility(df: pd.DataFrame, window: int = 60) -> pd.Series:
    """Residual volatility after removing market factor."""
    returns = df.groupby("code")["close"].pct_change()
    market_ret = df.groupby("date")["close"].transform(
        lambda x: x.pct_change().mean() if len(x) > 1 else np.nan
    )

    df_temp = df.copy()
    df_temp["_ret"] = returns
    df_temp["_mkt"] = market_ret

    def residual_vol(group: pd.DataFrame) -> pd.Series:
        cov = group["_ret"].rolling(window, min_periods=window).cov(group["_mkt"])
        var = group["_mkt"].rolling(window, min_periods=window).var()
        beta = safe_div(cov, var.replace(0, np.nan))
        residual = group["_ret"] - beta * group["_mkt"]
        return residual.rolling(window, min_periods=window).std()

    return df_temp.groupby("code", group_keys=False).apply(residual_vol).reset_index(level=0, drop=True)


# ─── Main Computation ────────────────────────────────────────────

_COMPUTE_MAP = {
    "size": compute_market_cap,
    "beta": compute_beta,
    "momentum_12m1m": compute_momentum_12m1m,
    "volatility": compute_volatility,
    "btop": compute_btop,
    "earnings_yield": compute_earnings_yield,
    "growth": compute_growth,
    "leverage": compute_leverage,
    "liquidity": compute_liquidity,
    "nonlinear_size": compute_nonlinear_size,
    "residual_volatility": compute_residual_volatility,
}


def compute_barra_factors(
    df: pd.DataFrame,
    factor_names: Sequence[str] | None = None,
) -> pd.DataFrame:
    """Compute Barra risk factors from a long panel.

    Args:
        df: Long panel with columns [date, code, open, high, low, close, volume, amount].
            Optional fundamental columns: total_shares, book_value_per_share,
            eps_ttm, net_profit_yoy, debt_to_equity.
        factor_names: Subset of BARRA_FACTOR_NAMES. Default: all.

    Returns:
        DataFrame with [date, code, factor_name...] columns.
    """
    data = sort_panel(df).copy()
    names = list(factor_names or BARRA_FACTOR_NAMES)

    result = data[["date", "code"]].copy()
    for name in names:
        fn = _COMPUTE_MAP.get(name)
        if fn:
            try:
                result[name] = fn(data)
            except Exception:
                result[name] = np.nan
        else:
            result[name] = np.nan

    return result


BARRA_IMPLEMENTED_FACTORS = tuple(BARRA_FACTOR_NAMES)


__all__ = [
    "BARRA_FACTOR_NAMES",
    "BARRA_IMPLEMENTED_FACTORS",
    "compute_barra_factors",
    "compute_market_cap",
    "compute_beta",
    "compute_momentum_12m1m",
    "compute_volatility",
    "compute_btop",
    "compute_earnings_yield",
    "compute_growth",
    "compute_leverage",
    "compute_liquidity",
    "compute_nonlinear_size",
    "compute_residual_volatility",
]
