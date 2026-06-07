from __future__ import annotations

import numpy as np
import pandas as pd


def sort_panel(df: pd.DataFrame, *, date_col: str = "date", code_col: str = "code") -> pd.DataFrame:
    data = df.copy()
    data[date_col] = pd.to_datetime(data[date_col])
    return data.sort_values([code_col, date_col]).reset_index(drop=True)


def safe_div(left: pd.Series, right: pd.Series | float | int) -> pd.Series:
    result = left.divide(right)
    return result.replace([np.inf, -np.inf], np.nan)


def cross_sectional_rank(
    df: pd.DataFrame,
    value_col: str,
    *,
    date_col: str = "date",
    ascending: bool = True,
) -> pd.Series:
    return df.groupby(date_col)[value_col].rank(method="average", pct=True, ascending=ascending)


def ts_delay(df: pd.DataFrame, value_col: str, periods: int, *, code_col: str = "code") -> pd.Series:
    return df.groupby(code_col)[value_col].shift(periods)


def ts_delta(df: pd.DataFrame, value_col: str, periods: int, *, code_col: str = "code") -> pd.Series:
    return df.groupby(code_col)[value_col].diff(periods)


def ts_sum(
    df: pd.DataFrame,
    value_col: str,
    window: int,
    *,
    code_col: str = "code",
    min_periods: int | None = None,
) -> pd.Series:
    min_obs = window if min_periods is None else min_periods
    return df.groupby(code_col)[value_col].transform(lambda x: x.rolling(window, min_periods=min_obs).sum())


def ts_mean(
    df: pd.DataFrame,
    value_col: str,
    window: int,
    *,
    code_col: str = "code",
    min_periods: int | None = None,
) -> pd.Series:
    min_obs = window if min_periods is None else min_periods
    return df.groupby(code_col)[value_col].transform(lambda x: x.rolling(window, min_periods=min_obs).mean())


def ts_std(
    df: pd.DataFrame,
    value_col: str,
    window: int,
    *,
    code_col: str = "code",
    min_periods: int | None = None,
) -> pd.Series:
    min_obs = window if min_periods is None else min_periods
    return df.groupby(code_col)[value_col].transform(lambda x: x.rolling(window, min_periods=min_obs).std(ddof=0))


def ts_min(
    df: pd.DataFrame,
    value_col: str,
    window: int,
    *,
    code_col: str = "code",
    min_periods: int | None = None,
) -> pd.Series:
    min_obs = window if min_periods is None else min_periods
    return df.groupby(code_col)[value_col].transform(lambda x: x.rolling(window, min_periods=min_obs).min())


def ts_max(
    df: pd.DataFrame,
    value_col: str,
    window: int,
    *,
    code_col: str = "code",
    min_periods: int | None = None,
) -> pd.Series:
    min_obs = window if min_periods is None else min_periods
    return df.groupby(code_col)[value_col].transform(lambda x: x.rolling(window, min_periods=min_obs).max())


def ts_rank(
    df: pd.DataFrame,
    value_col: str,
    window: int,
    *,
    code_col: str = "code",
    min_periods: int | None = None,
) -> pd.Series:
    min_obs = window if min_periods is None else min_periods

    def _rank_last(values: np.ndarray) -> float:
        series = pd.Series(values)
        return float(series.rank(method="average", pct=True).iloc[-1])

    return df.groupby(code_col)[value_col].transform(
        lambda x: x.rolling(window, min_periods=min_obs).apply(_rank_last, raw=True)
    )


def ts_argmax(
    df: pd.DataFrame,
    value_col: str,
    window: int,
    *,
    code_col: str = "code",
    min_periods: int | None = None,
) -> pd.Series:
    min_obs = window if min_periods is None else min_periods
    return df.groupby(code_col)[value_col].transform(
        lambda x: x.rolling(window, min_periods=min_obs).apply(np.argmax, raw=True)
    )


def ts_argmin(
    df: pd.DataFrame,
    value_col: str,
    window: int,
    *,
    code_col: str = "code",
    min_periods: int | None = None,
) -> pd.Series:
    min_obs = window if min_periods is None else min_periods
    return df.groupby(code_col)[value_col].transform(
        lambda x: x.rolling(window, min_periods=min_obs).apply(np.argmin, raw=True)
    )


def ts_product(
    df: pd.DataFrame,
    value_col: str,
    window: int,
    *,
    code_col: str = "code",
    min_periods: int | None = None,
) -> pd.Series:
    min_obs = window if min_periods is None else min_periods
    return df.groupby(code_col)[value_col].transform(
        lambda x: x.rolling(window, min_periods=min_obs).apply(np.prod, raw=True)
    )


def rolling_corr(
    df: pd.DataFrame,
    left_col: str,
    right_col: str,
    window: int,
    *,
    code_col: str = "code",
    min_periods: int | None = None,
) -> pd.Series:
    min_obs = window if min_periods is None else min_periods
    pieces: list[pd.Series] = []
    for _, group in df.groupby(code_col, sort=False):
        corr = group[left_col].rolling(window, min_periods=min_obs).corr(group[right_col])
        corr.index = group.index
        pieces.append(corr)
    return pd.concat(pieces).sort_index() if pieces else pd.Series(dtype=float)


def rolling_cov(
    df: pd.DataFrame,
    left_col: str,
    right_col: str,
    window: int,
    *,
    code_col: str = "code",
    min_periods: int | None = None,
) -> pd.Series:
    min_obs = window if min_periods is None else min_periods
    pieces: list[pd.Series] = []
    for _, group in df.groupby(code_col, sort=False):
        cov = group[left_col].rolling(window, min_periods=min_obs).cov(group[right_col])
        cov.index = group.index
        pieces.append(cov)
    return pd.concat(pieces).sort_index() if pieces else pd.Series(dtype=float)


def ts_decay_linear(
    df: pd.DataFrame,
    value_col: str,
    window: int,
    *,
    code_col: str = "code",
    min_periods: int | None = None,
) -> pd.Series:
    min_obs = window if min_periods is None else min_periods

    def _decay(values: np.ndarray) -> float:
        mask = ~np.isnan(values)
        if not mask.any():
            return np.nan
        valid_values = values[mask]
        valid_weights = np.arange(1, len(values) + 1, dtype=float)[mask]
        return float(np.dot(valid_values, valid_weights) / valid_weights.sum())

    return df.groupby(code_col)[value_col].transform(
        lambda x: x.rolling(window, min_periods=min_obs).apply(_decay, raw=True)
    )


def cross_sectional_scale(
    df: pd.DataFrame,
    value_col: str,
    *,
    date_col: str = "date",
    scale: float = 1.0,
) -> pd.Series:
    def _scale(group: pd.Series) -> pd.Series:
        denom = group.abs().sum()
        if pd.isna(denom) or denom == 0:
            return group * 0.0
        return group / denom * scale

    return df.groupby(date_col)[value_col].transform(_scale)


def indneutralize(
    df: pd.DataFrame,
    value_col: str,
    group_col: str,
    *,
    date_col: str = "date",
) -> pd.Series:
    return df[value_col] - df.groupby([date_col, group_col])[value_col].transform("mean")


def compute_vwap(
    df: pd.DataFrame,
    *,
    amount_col: str = "amount",
    volume_col: str = "volume",
    fallback_cols: tuple[str, str, str, str] = ("open", "high", "low", "close"),
) -> pd.Series:
    amount = df[amount_col]
    volume = df[volume_col]
    vwap = safe_div(amount, volume.replace(0, np.nan))
    if all(col in df.columns for col in fallback_cols):
        open_, high, low, close = (df[col] for col in fallback_cols)
        fallback = (open_ + high + low + close) / 4.0
        vwap = vwap.fillna(fallback)
        mask = volume.isna() | (volume == 0)
        vwap = vwap.where(~mask, fallback)
    return vwap
