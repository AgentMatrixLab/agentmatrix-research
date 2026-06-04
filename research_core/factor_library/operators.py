# ============================================================
# Factor Operators - 因子基础操作函数
# ============================================================

import numpy as np
import pandas as pd
from scipy.stats import rankdata


def cross_sectional_rank(df: pd.DataFrame, date_col: str, value_col: str) -> pd.Series:
    """Return percentile rank of ``value_col`` within each ``date_col`` cross-section."""
    return df.groupby(date_col)[value_col].rank(pct=True)


def rank_cross_section(df, col):
    """RANK: 截面百分位排名"""
    return cross_sectional_rank(df, 'date', col)


def ts_rank(series: pd.Series, window: int) -> pd.Series:
    """Return rolling percentile rank of the last value in each window."""
    def _rank_last(x):
        return rankdata(x)[-1] / len(x)
    return series.rolling(window).apply(_rank_last, raw=True)


def tsrank(series, n):
    """Ts_Rank / TSRANK: 末位值在过去n天的百分位排名"""
    return ts_rank(series, n)


def ts_corr(x, y=None, window=None, n=None):
    """correlation / CORR: 滚动相关系数"""
    if isinstance(x, pd.DataFrame):
        group = x
        col_a = y
        col_b = window
        corr_window = n
        return group[col_a].rolling(corr_window).corr(group[col_b])
    corr_window = window if window is not None else n
    return x.rolling(corr_window).corr(y)


def delta(series: pd.Series, period: int) -> pd.Series:
    """DELTA: n阶差分"""
    return series.diff(period)


def delay(series: pd.Series, period: int) -> pd.Series:
    """DELAY: n期滞后"""
    return series.shift(period)


def ts_sum(series: pd.Series, window: int) -> pd.Series:
    """Return rolling sum."""
    return series.rolling(window).sum()


def ts_mean(series: pd.Series, window: int) -> pd.Series:
    """Return rolling mean."""
    return series.rolling(window).mean()


def ts_std(series: pd.Series, window: int) -> pd.Series:
    """Return rolling standard deviation."""
    return series.rolling(window).std()


def ts_min(series: pd.Series, window: int) -> pd.Series:
    """Return rolling minimum."""
    return series.rolling(window).min()


def ts_max(series: pd.Series, window: int) -> pd.Series:
    """Return rolling maximum."""
    return series.rolling(window).max()


def tsmax(series, n):
    """ts_max / TSMAX: 滚动最大值"""
    return ts_max(series, n)


def tsmin(series, n):
    """ts_min / TSMIN: 滚动最小值"""
    return ts_min(series, n)


def ts_argmax(series, n):
    """Ts_ArgMax: 过去n天最大值所在位置(0-based)"""
    return series.rolling(n).apply(np.argmax, raw=True)


def signed_power(series: pd.Series, power: float) -> pd.Series:
    """Return sign-preserving power transform."""
    return np.sign(series) * (np.abs(series) ** power)


def safe_vwap(
    amount: pd.Series,
    volume: pd.Series,
    open_: pd.Series,
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
) -> pd.Series:
    """Return VWAP as amount / volume, falling back to OHLC mean when invalid."""
    vwap = amount / volume
    vwap = vwap.replace([np.inf, -np.inf], np.nan)
    ohlc_mean = (open_ + high + low + close) / 4
    vwap = vwap.fillna(ohlc_mean)
    mask_zero_vol = (volume == 0) | volume.isna()
    vwap[mask_zero_vol] = ohlc_mean[mask_zero_vol]
    return vwap


def compute_vwap(close, high, low, open_, amount, volume):
    """计算VWAP: amount/volume，零值用OHLC均值填充"""
    return safe_vwap(amount, volume, open_, high, low, close)


def sma_gtja(series, n, m):
    """GTJA191 SMA: Y_{i+1} = (A_i * m + Y_i * (n - m)) / n"""
    values = series.values.astype(float)
    result = np.full(len(values), np.nan)
    start_idx = 0
    for i in range(len(values)):
        if not np.isnan(values[i]):
            result[i] = values[i]
            start_idx = i
            break
    for i in range(start_idx + 1, len(values)):
        if np.isnan(values[i]):
            result[i] = result[i - 1]
        else:
            result[i] = (values[i] * m + result[i - 1] * (n - m)) / n
    return pd.Series(result, index=series.index)
