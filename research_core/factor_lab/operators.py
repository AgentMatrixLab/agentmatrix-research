"""AgentMatrix Research factor-lab operators mirrored for local factor work.

The long-panel operators stay aligned with the AgentMatrix Research operator
surface.  Local wide date x symbol extensions live here too, so GTJA191 and
future backtests can use ``research_core.factor_lab.operators`` as the single
operator layer.

Source:
https://github.com/AgentMatrixLab/agentmatrix-research/blob/main/research_core/factor_lab/operators.py
Fetched on 2026-06-10 from the public Apache-2.0 repository.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class SequenceSpec:
    """Placeholder for SEQUENCE(n) regression inputs."""

    length: int | None = None


def as_window(window: float | int) -> int:
    """Convert formula window arguments to positive integer windows."""
    result = int(math.floor(float(window)))
    if result <= 0:
        raise ValueError("window must be at least 1")
    return result


def panel_to_wide(
    data: pd.DataFrame,
    value_col: str,
    date_col: str = "date",
    symbol_col: str = "symbol",
) -> pd.DataFrame:
    """Convert a long panel to a date x symbol matrix."""
    required = {date_col, symbol_col, value_col}
    missing = required.difference(data.columns)
    if missing:
        missing_list = ", ".join(sorted(missing))
        raise ValueError(f"Missing required column(s): {missing_list}")

    frame = data[[date_col, symbol_col, value_col]].copy()
    frame[date_col] = pd.to_datetime(frame[date_col])
    wide = frame.pivot_table(
        index=date_col,
        columns=symbol_col,
        values=value_col,
        aggfunc="last",
    )
    return wide.sort_index().sort_index(axis=1)


def sort_panel(df: pd.DataFrame, *, date_col: str = "date", code_col: str = "code") -> pd.DataFrame:
    data = df.copy()
    data[date_col] = pd.to_datetime(data[date_col])
    return data.sort_values([code_col, date_col]).reset_index(drop=True)


def align_sort(*frames: pd.DataFrame) -> tuple[pd.DataFrame, ...]:
    """Align date indexes and symbol columns for formula arithmetic."""
    index = frames[0].index
    columns = frames[0].columns
    for frame in frames[1:]:
        index = index.union(frame.index)
        columns = columns.union(frame.columns)
    index = index.sort_values()
    columns = columns.sort_values()
    return tuple(frame.reindex(index=index, columns=columns) for frame in frames)


def safe_div(left: pd.Series, right: pd.Series | float | int) -> pd.Series:
    result = left.divide(right)
    return result.replace([np.inf, -np.inf], np.nan)


def signed_power(values: pd.DataFrame, power: float | pd.DataFrame) -> pd.DataFrame:
    """Raise absolute values to a power while preserving signs."""
    return np.sign(values) * np.power(np.abs(values), power)


def returns_from_close(close: pd.DataFrame) -> pd.DataFrame:
    """Simple close-to-close returns by symbol."""
    return close.sort_index().pct_change(fill_method=None)


def delta(values: pd.DataFrame, periods: int = 1) -> pd.DataFrame:
    """Difference from ``periods`` observations ago by symbol."""
    periods = as_window(periods)
    return values - values.shift(periods)


def cross_sectional_rank(
    df: pd.DataFrame,
    value_col: str | None = None,
    *,
    date_col: str = "date",
    ascending: bool = True,
) -> pd.Series | pd.DataFrame:
    if value_col is None:
        return df.rank(axis=1, method="average", pct=True, ascending=ascending)
    return df.groupby(date_col)[value_col].rank(method="average", pct=True, ascending=ascending)


def ts_delay(df: pd.DataFrame, value_col: str, periods: int, *, code_col: str = "code") -> pd.Series:
    return df.groupby(code_col)[value_col].shift(as_window(periods))


def ts_delta(df: pd.DataFrame, value_col: str, periods: int, *, code_col: str = "code") -> pd.Series:
    return df.groupby(code_col)[value_col].diff(as_window(periods))


def ts_sum(
    df: pd.DataFrame,
    value_col: str,
    window: int,
    *,
    code_col: str = "code",
    min_periods: int | None = None,
) -> pd.Series:
    window = as_window(window)
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
    window = as_window(window)
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
    window = as_window(window)
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
    window = as_window(window)
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
    window = as_window(window)
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
    window = as_window(window)
    min_obs = window if min_periods is None else min_periods

    def _rank_last(values: np.ndarray) -> float:
        series = pd.Series(values)
        return float(series.rank(method="average", pct=True).iloc[-1])

    return df.groupby(code_col)[value_col].transform(
        lambda x: x.rolling(window, min_periods=min_obs).apply(_rank_last, raw=True)
    )


def ts_argmax(
    df: pd.DataFrame,
    value_col: str | float | int | None = None,
    window: float | int | None = None,
    *,
    code_col: str = "code",
    min_periods: int | None = None,
) -> pd.Series | pd.DataFrame:
    """1-based position of the rolling-window maximum."""
    if window is None:
        window = value_col
        value_col = None
    window = as_window(window)
    min_obs = window if min_periods is None else min_periods

    def _argmax_1based(values: np.ndarray) -> float:
        if np.isnan(values).any():
            return np.nan
        return float(np.argmax(values) + 1)

    if value_col is None:
        return df.rolling(window, min_periods=min_obs).apply(_argmax_1based, raw=True)
    return df.groupby(code_col)[str(value_col)].transform(
        lambda x: x.rolling(window, min_periods=min_obs).apply(_argmax_1based, raw=True)
    )


def ts_argmin(
    df: pd.DataFrame,
    value_col: str | float | int | None = None,
    window: float | int | None = None,
    *,
    code_col: str = "code",
    min_periods: int | None = None,
) -> pd.Series | pd.DataFrame:
    """1-based position of the rolling-window minimum."""
    if window is None:
        window = value_col
        value_col = None
    window = as_window(window)
    min_obs = window if min_periods is None else min_periods

    def _argmin_1based(values: np.ndarray) -> float:
        if np.isnan(values).any():
            return np.nan
        return float(np.argmin(values) + 1)

    if value_col is None:
        return df.rolling(window, min_periods=min_obs).apply(_argmin_1based, raw=True)
    return df.groupby(code_col)[str(value_col)].transform(
        lambda x: x.rolling(window, min_periods=min_obs).apply(_argmin_1based, raw=True)
    )


def ts_product(
    df: pd.DataFrame,
    value_col: str,
    window: int,
    *,
    code_col: str = "code",
    min_periods: int | None = None,
) -> pd.Series:
    window = as_window(window)
    min_obs = window if min_periods is None else min_periods
    return df.groupby(code_col)[value_col].transform(
        lambda x: x.rolling(window, min_periods=min_obs).apply(np.prod, raw=True)
    )


def rolling_corr(
    df: pd.DataFrame,
    left_col: str | pd.DataFrame,
    right_col: str | float | int | None = None,
    window: float | int | None = None,
    *,
    code_col: str = "code",
    min_periods: int | None = None,
) -> pd.Series | pd.DataFrame:
    if isinstance(left_col, pd.DataFrame):
        if window is None:
            if right_col is None:
                raise ValueError("window is required for wide rolling_corr")
            window = right_col
        window = as_window(window)
        min_obs = window if min_periods is None else min_periods
        left, right = df.align(left_col, join="outer")
        return left.rolling(window=window, min_periods=min_obs).corr(right)

    if right_col is None or window is None:
        raise ValueError("right_col and window are required for long-panel rolling_corr")
    window = as_window(window)
    min_obs = window if min_periods is None else min_periods
    pieces: list[pd.Series] = []
    for _, group in df.groupby(code_col, sort=False):
        corr = group[left_col].rolling(window, min_periods=min_obs).corr(group[str(right_col)])
        corr.index = group.index
        pieces.append(corr)
    return pd.concat(pieces).sort_index() if pieces else pd.Series(dtype=float)


def rolling_cov(
    df: pd.DataFrame,
    left_col: str | pd.DataFrame,
    right_col: str | float | int | None = None,
    window: float | int | None = None,
    *,
    code_col: str = "code",
    min_periods: int | None = None,
) -> pd.Series | pd.DataFrame:
    if isinstance(left_col, pd.DataFrame):
        if window is None:
            if right_col is None:
                raise ValueError("window is required for wide rolling_cov")
            window = right_col
        window = as_window(window)
        min_obs = window if min_periods is None else min_periods
        left, right = df.align(left_col, join="outer")
        return left.rolling(window=window, min_periods=min_obs).cov(right)

    if right_col is None or window is None:
        raise ValueError("right_col and window are required for long-panel rolling_cov")
    window = as_window(window)
    min_obs = window if min_periods is None else min_periods
    pieces: list[pd.Series] = []
    for _, group in df.groupby(code_col, sort=False):
        cov = group[left_col].rolling(window, min_periods=min_obs).cov(group[str(right_col)])
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
    window = as_window(window)
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
    value_col: str | float | int | None = None,
    *,
    date_col: str = "date",
    scale: float = 1.0,
) -> pd.Series | pd.DataFrame:
    if value_col is None or not isinstance(value_col, str):
        target = scale if value_col is None else float(value_col)
        denominator = df.abs().sum(axis=1).replace(0.0, np.nan)
        return df.div(denominator, axis=0) * float(target)

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


def rolling_mean(
    values: pd.DataFrame,
    window: float | int,
    min_periods: int | None = None,
) -> pd.DataFrame:
    """Rolling mean with full-window default."""
    window = as_window(window)
    if min_periods is None:
        min_periods = window
    return values.rolling(window=window, min_periods=min_periods).mean()


def rolling_sum(
    values: pd.DataFrame,
    window: float | int,
    min_periods: int | None = None,
) -> pd.DataFrame:
    """Rolling sum with full-window default."""
    window = as_window(window)
    if min_periods is None:
        min_periods = window
    return values.rolling(window=window, min_periods=min_periods).sum()


def rolling_min(
    values: pd.DataFrame,
    window: float | int,
    min_periods: int | None = None,
) -> pd.DataFrame:
    """Rolling minimum with full-window default."""
    window = as_window(window)
    if min_periods is None:
        min_periods = window
    return values.rolling(window=window, min_periods=min_periods).min()


def rolling_max(
    values: pd.DataFrame,
    window: float | int,
    min_periods: int | None = None,
) -> pd.DataFrame:
    """Rolling maximum with full-window default."""
    window = as_window(window)
    if min_periods is None:
        min_periods = window
    return values.rolling(window=window, min_periods=min_periods).max()


def rolling_std(
    values: pd.DataFrame,
    window: float | int,
    min_periods: int | None = None,
    ddof: int = 1,
) -> pd.DataFrame:
    """Rolling standard deviation with full-window default."""
    window = as_window(window)
    if min_periods is None:
        min_periods = window
    return values.rolling(window=window, min_periods=min_periods).std(ddof=ddof)


def rolling_product(
    values: pd.DataFrame,
    window: float | int,
    min_periods: int | None = None,
) -> pd.DataFrame:
    """Rolling product with full-window default."""
    window = as_window(window)
    if min_periods is None:
        min_periods = window
    return values.rolling(window=window, min_periods=min_periods).apply(
        np.prod,
        raw=True,
    )


def time_series_rank(values: pd.DataFrame, window: float | int) -> pd.DataFrame:
    """Percentile rank of the latest value inside each rolling window."""
    window = as_window(window)

    def latest_percentile_rank(window_values: np.ndarray) -> float:
        if np.isnan(window_values).any():
            return np.nan
        latest = window_values[-1]
        less_count = np.sum(window_values < latest)
        equal_count = np.sum(window_values == latest)
        average_rank = less_count + (equal_count + 1.0) / 2.0
        return float(average_rank / len(window_values))

    return values.rolling(window=window, min_periods=window).apply(
        latest_percentile_rank,
        raw=True,
    )


def highday(values: pd.DataFrame, window: float | int) -> pd.DataFrame:
    """Days since the rolling-window high, where current day is 0."""
    window = as_window(window)

    def distance(window_values: np.ndarray) -> float:
        if np.isnan(window_values).any():
            return np.nan
        return float(window - 1 - int(np.argmax(window_values)))

    return values.rolling(window=window, min_periods=window).apply(distance, raw=True)


def lowday(values: pd.DataFrame, window: float | int) -> pd.DataFrame:
    """Days since the rolling-window low, where current day is 0."""
    window = as_window(window)

    def distance(window_values: np.ndarray) -> float:
        if np.isnan(window_values).any():
            return np.nan
        return float(window - 1 - int(np.argmin(window_values)))

    return values.rolling(window=window, min_periods=window).apply(distance, raw=True)


def decay_linear(values: pd.DataFrame, window: float | int) -> pd.DataFrame:
    """Linearly weighted moving average with the newest value weighted highest."""
    window = as_window(window)
    weights = np.arange(1.0, window + 1.0)
    weights = weights / weights.sum()

    def weighted_average(window_values: np.ndarray) -> float:
        if np.isnan(window_values).any():
            return np.nan
        return float(np.dot(window_values, weights))

    return values.rolling(window=window, min_periods=window).apply(
        weighted_average,
        raw=True,
    )


def wma(values: pd.DataFrame, window: float | int) -> pd.DataFrame:
    """Weighted moving average with 0.9**distance weights."""
    window = as_window(window)
    weights = np.power(0.9, np.arange(window - 1, -1, -1, dtype=float))
    weights = weights / weights.sum()

    def weighted_average(window_values: np.ndarray) -> float:
        if np.isnan(window_values).any():
            return np.nan
        return float(np.dot(window_values, weights))

    return values.rolling(window=window, min_periods=window).apply(
        weighted_average,
        raw=True,
    )


def sma(values: pd.DataFrame, window: float | int, weight: float | int) -> pd.DataFrame:
    """Chinese-style recursive SMA: Y_t = (m*A_t + (n-m)*Y_{t-1}) / n."""
    window = float(as_window(window))
    weight = float(weight)
    result = pd.DataFrame(np.nan, index=values.index, columns=values.columns)

    for column in values.columns:
        previous = np.nan
        output: list[float] = []
        for value in values[column].to_numpy(dtype=float):
            if np.isnan(value):
                output.append(np.nan)
                continue
            if np.isnan(previous):
                previous = value
            else:
                previous = (weight * value + (window - weight) * previous) / window
            output.append(previous)
        result[column] = output
    return result


def rolling_count(condition: pd.DataFrame, window: float | int) -> pd.DataFrame:
    """Count true observations over a rolling window."""
    return rolling_sum(condition.astype(float), window)


def rolling_sumif(
    values: pd.DataFrame,
    window: float | int,
    condition: pd.DataFrame,
) -> pd.DataFrame:
    """Rolling sum of values where condition is true."""
    values, condition = values.align(condition, join="outer")
    return rolling_sum(values.where(condition.astype(bool), 0.0), window)


def filter_values(values: pd.DataFrame, condition: pd.DataFrame) -> pd.DataFrame:
    """Keep observations satisfying condition and mask the rest."""
    values, condition = values.align(condition, join="outer")
    return values.where(condition.astype(bool))


def sumac(values: pd.DataFrame, window: float | int | None = None) -> pd.DataFrame:
    """Cumulative sum, or rolling sum if a window is supplied."""
    if window is None:
        return values.cumsum()
    return rolling_sum(values, window)


def rolling_regression_beta(
    y: pd.DataFrame,
    x: pd.DataFrame | Sequence[pd.DataFrame] | SequenceSpec,
    window: float | int | None = None,
) -> pd.DataFrame:
    """Rolling OLS beta of y on x; returns the latest slope coefficient."""
    if isinstance(x, SequenceSpec):
        window = as_window(window or x.length or 1)
        return _rolling_beta_against_sequence(y, window)

    if isinstance(x, Sequence) and not isinstance(x, pd.DataFrame):
        xs = [frame for frame in x if isinstance(frame, pd.DataFrame)]
        if window is None:
            raise ValueError("multi-factor REGBETA requires a window")
        return _rolling_multivariate_ols(y, xs, as_window(window), residual=False)

    if window is None:
        raise ValueError("REGBETA requires a regression window")

    return _rolling_multivariate_ols(y, [x], as_window(window), residual=False)


def rolling_regression_residual(
    y: pd.DataFrame,
    xs: Sequence[pd.DataFrame] | pd.DataFrame | SequenceSpec,
    window: float | int,
) -> pd.DataFrame:
    """Rolling OLS residual for the latest observation in each window."""
    window = as_window(window)
    if isinstance(xs, SequenceSpec):
        beta = _rolling_beta_against_sequence(y, window)
        sequence_latest = float(window)
        intercept = rolling_mean(y, window) - beta * (window + 1.0) / 2.0
        return y - (intercept + beta * sequence_latest)
    if isinstance(xs, pd.DataFrame):
        return _rolling_multivariate_ols(y, [xs], window, residual=True)
    return _rolling_multivariate_ols(y, list(xs), window, residual=True)


def _rolling_beta_against_sequence(y: pd.DataFrame, window: int) -> pd.DataFrame:
    x_values = np.arange(1.0, window + 1.0)
    x_centered = x_values - x_values.mean()
    denominator = float(np.dot(x_centered, x_centered))

    def beta(window_values: np.ndarray) -> float:
        if np.isnan(window_values).any():
            return np.nan
        y_centered = window_values - window_values.mean()
        return float(np.dot(x_centered, y_centered) / denominator)

    return y.rolling(window=window, min_periods=window).apply(beta, raw=True)


def _rolling_multivariate_ols(
    y: pd.DataFrame,
    xs: Sequence[pd.DataFrame],
    window: int,
    residual: bool,
) -> pd.DataFrame:
    frames = align_sort(y, *xs)
    y = frames[0]
    xs = frames[1:]
    result = pd.DataFrame(np.nan, index=y.index, columns=y.columns)

    for column in y.columns:
        y_values = y[column].to_numpy(dtype=float)
        x_values = [x[column].to_numpy(dtype=float) for x in xs]
        output = np.full(len(y_values), np.nan, dtype=float)
        for end in range(window - 1, len(y_values)):
            start = end - window + 1
            y_window = y_values[start : end + 1]
            x_window = np.column_stack([xv[start : end + 1] for xv in x_values])
            valid = np.isfinite(y_window) & np.isfinite(x_window).all(axis=1)
            if int(valid.sum()) < len(xs) + 2:
                continue
            design = np.column_stack([np.ones(int(valid.sum())), x_window[valid]])
            coefficients, *_ = np.linalg.lstsq(design, y_window[valid], rcond=None)
            if residual:
                latest_x = np.array([1.0, *[xv[end] for xv in x_values]], dtype=float)
                if np.isfinite(latest_x).all() and np.isfinite(y_values[end]):
                    output[end] = y_values[end] - float(latest_x @ coefficients)
            else:
                output[end] = coefficients[1] if len(coefficients) > 1 else np.nan
        result[column] = output
    return result


def industry_neutralize(
    values: pd.DataFrame,
    groups: Mapping[str, object] | pd.Series | pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Cross-sectionally demean values within group labels."""
    if groups is None:
        return values.copy()

    if isinstance(groups, Mapping):
        labels = pd.Series(groups)
    elif isinstance(groups, pd.Series):
        labels = groups
    elif isinstance(groups, pd.DataFrame):
        labels = groups.reindex(index=values.index, columns=values.columns)
    else:
        return values.copy()

    result = values.astype(float).copy()
    if isinstance(labels, pd.Series):
        labels = labels.reindex(values.columns)
        for group in labels.dropna().unique():
            columns = labels.index[labels == group]
            result.loc[:, columns] = result.loc[:, columns].sub(
                result.loc[:, columns].mean(axis=1),
                axis=0,
            )
        return result

    for date in values.index:
        row_labels = labels.loc[date]
        for group in row_labels.dropna().unique():
            columns = row_labels.index[row_labels == group]
            result.loc[date, columns] = result.loc[date, columns] - result.loc[
                date,
                columns,
            ].mean()
    return result


__all__ = [
    "SequenceSpec",
    "align_sort",
    "as_window",
    "compute_vwap",
    "cross_sectional_rank",
    "cross_sectional_scale",
    "decay_linear",
    "delta",
    "filter_values",
    "highday",
    "indneutralize",
    "industry_neutralize",
    "lowday",
    "panel_to_wide",
    "returns_from_close",
    "rolling_corr",
    "rolling_count",
    "rolling_cov",
    "rolling_max",
    "rolling_mean",
    "rolling_min",
    "rolling_product",
    "rolling_regression_beta",
    "rolling_regression_residual",
    "rolling_std",
    "rolling_sum",
    "rolling_sumif",
    "safe_div",
    "signed_power",
    "sma",
    "sort_panel",
    "sumac",
    "time_series_rank",
    "ts_argmax",
    "ts_argmin",
    "ts_decay_linear",
    "ts_delay",
    "ts_delta",
    "ts_max",
    "ts_mean",
    "ts_min",
    "ts_product",
    "ts_rank",
    "ts_std",
    "ts_sum",
    "wma",
]
