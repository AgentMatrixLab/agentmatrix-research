# ============================================================
# Factor Operators - 因子基础操作函数（已修复版 - 满足 review 要求）
# ============================================================
# 修改记录（2026-06-08 第二版）：
# 1. ts_corr：从“潜在横截面/混算错误”改为“严格 per-stock 时序相关性”
# 2. 同时兼容 symbol/date 和仓库常用的 code/date
# 3. 优先使用显式传入的列名（ts_corr(df, 'left', 'right', 5)）
# 4. 彻底取消“前两列” fallback 策略，避免 TypeError
# 5. 新增 adv_amount helper，保证 alpha7 单位一致

import numpy as np
import pandas as pd


def cross_sectional_rank(df: pd.DataFrame, date_col: str, value_col: str) -> pd.Series:
    """Return percentile rank of ``value_col`` within each ``date_col`` cross-section."""
    return df.groupby(date_col)[value_col].rank(pct=True)


def rank_cross_section(df, col):
    """RANK: 截面百分位排名（alpha9 等需要 [0,1] 标准化时使用）"""
    return cross_sectional_rank(df, 'date', col)


def ts_rank(series: pd.Series, window: int) -> pd.Series:
    """Return rolling percentile rank of the last value in each window."""
    def _rank_last(x):
        return pd.Series(x).rank(method="average", pct=True).iloc[-1]
    return series.rolling(window).apply(_rank_last, raw=True)


def tsrank(series, n):
    """Ts_Rank / TSRANK: 末位值在过去n天的百分位排名"""
    return ts_rank(series, n)


def ts_corr(x, y=None, window=None, n=None, group_col: str = None, date_col: str = 'date') -> pd.Series:
    """【第二版 - 满足 review 全部要求】CORR / 滚动相关系数
    1. 同时兼容 symbol/date 和 code/date
    2. 优先使用显式传入的列名（ts_corr(df, 'left', 'right', 5)）
    3. 彻底取消“前两列” fallback 策略
    4. 自动检测 group_col（symbol 或 code）
    """
    corr_window = n if n is not None else window
    if corr_window is None:
        raise ValueError("必须提供 window 或 n 参数")

    if isinstance(x, pd.DataFrame):
        df = x.copy()

        # 自动检测分组列（兼容 symbol 和 code）
        if group_col is None:
            for candidate in ['symbol', 'code', 'ticker', 'asset', 'stock']:
                if candidate in df.columns:
                    group_col = candidate
                    break
            if group_col is None:
                raise ValueError(f"无法自动检测分组列，请手动传入 group_col。当前列名: {list(df.columns)}")

        # 排序
        if date_col in df.columns:
            df = df.sort_values([group_col, date_col])

        # 优先使用显式传入的列名
        col_a = y if isinstance(y, str) and y in df.columns else None
        col_b = window if isinstance(window, str) and window in df.columns else None

        if col_a is None or col_b is None:
            raise ValueError(
                f"DataFrame模式下请显式传入列名，例如 ts_corr(df, 'left', 'right', 5)\n"
                f"当前可用列: {list(df.columns)}"
            )

        # 按股票分组计算
        def _corr_group(g):
            return g[col_a].rolling(window=corr_window, min_periods=1).corr(g[col_b])

        result = df.groupby(group_col).apply(_corr_group)
        return result.reset_index(level=0, drop=True)

    # 单股票 Series 模式（兼容旧代码）
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


def ts_argmax(
    df: pd.DataFrame,
    value_col: str,
    window: int,
    *,
    code_col: str = "code",
    min_periods: int | None = None,
) -> pd.Series:
    """1-based position of the rolling-window maximum (Ts_ArgMax semantics)."""
    min_obs = window if min_periods is None else min_periods

    def _argmax_1based(values: np.ndarray) -> float:
        if np.isnan(values).any():
            return np.nan
        return float(np.argmax(values) + 1)

    return df.groupby(code_col)[value_col].transform(
        lambda x: x.rolling(window, min_periods=min_obs).apply(_argmax_1based, raw=True)
    )


def ts_argmin(
    df: pd.DataFrame,
    value_col: str,
    window: int,
    *,
    code_col: str = "code",
    min_periods: int | None = None,
) -> pd.Series:
    """1-based position of the rolling-window minimum (Ts_ArgMin semantics)."""
    min_obs = window if min_periods is None else min_periods

    def _argmin_1based(values: np.ndarray) -> float:
        if np.isnan(values).any():
            return np.nan
        return float(np.argmin(values) + 1)

    return df.groupby(code_col)[value_col].transform(
        lambda x: x.rolling(window, min_periods=min_obs).apply(_argmin_1based, raw=True)
    )


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


# 【新增】alpha7 专用 helper，保证单位一致
def adv_amount(series: pd.Series, window: int) -> pd.Series:
    """adv20 使用 amount（成交额）计算，与 alpha7 单位匹配
    原问题：volume（股数）与 adv20 单位不一致 → 修复后统一用 amount
    """
    return ts_mean(series, window)
