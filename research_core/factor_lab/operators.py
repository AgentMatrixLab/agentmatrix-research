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
from numpy.lib.stride_tricks import sliding_window_view


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


def safe_div(left: pd.Series | float | int, right: pd.Series | float | int) -> pd.Series | float:
    """Divide, tolerating a scalar on either side.

    ALPHA101 writes reciprocals as ``1 / close``, which reaches here with a float
    on the left. ``float.divide`` does not exist, so the scalar is promoted to a
    Series carrying the other operand's index rather than failing.
    """
    if isinstance(left, (pd.Series, pd.DataFrame)):
        result = left.divide(right)
    elif isinstance(right, (pd.Series, pd.DataFrame)):
        result = pd.Series(left, index=right.index).divide(right)
    else:
        return (left / right) if right else float("nan")
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
    """Rolling percentile rank of the current bar within its trailing window.

    Vectorised deliberately. The obvious implementation -- ``rolling(w).apply``
    with a Python callback that builds a Series and calls ``.rank()`` -- costs
    roughly 250 microseconds per bar per call, and `TS_RANK` appears in a large
    share of ALPHA101 and GTJA191. Measured on a 121,640-row panel it made 12 of
    60 catalog expressions take 80% of the total runtime, with the worst at 96
    seconds for one factor.

    For a full window the average-rank percentile of the last element is exactly
    ``(less + (equal + 1) / 2) / window`` where ``less`` counts strictly smaller
    values and ``equal`` counts ties including itself, which is what pandas'
    ``rank(method="average", pct=True)`` returns. Both counts are available from a
    single sliding-window comparison, so the whole column is computed in numpy.

    A partial window (``min_periods < window``) falls back to the per-window path,
    because the vectorised form assumes full windows. The compiler never asks for
    one: it emits the window with no ``min_periods``.
    """
    window = as_window(window)
    min_obs = window if min_periods is None else min_periods

    if min_obs != window:
        def _rank_last(values: np.ndarray) -> float:
            series = pd.Series(values)
            return float(series.rank(method="average", pct=True).iloc[-1])

        return df.groupby(code_col)[value_col].transform(
            lambda x: x.rolling(window, min_periods=min_obs).apply(_rank_last, raw=True)
        )

    values = df[value_col].to_numpy(dtype=float)
    result = np.full(len(df), np.nan, dtype=float)

    for positions in df.groupby(code_col, sort=False).indices.values():
        series = values[positions]
        n = len(series)
        if n < window:
            continue
        windows = sliding_window_view(series, window)
        last = windows[:, -1]
        less = (windows < last[:, None]).sum(axis=1)
        equal = (windows == last[:, None]).sum(axis=1)
        percentile = (less + (equal + 1) / 2.0) / window
        complete = ~np.isnan(windows).any(axis=1)
        result[positions[window - 1 :]] = np.where(complete, percentile, np.nan)

    return pd.Series(result, index=df.index)


def _rolling_extreme_position(values: np.ndarray, window: int, *, find_max: bool) -> np.ndarray:
    """1-based position of the extreme in each full trailing window.

    Vectorised replacement for ``rolling(w).apply(np.argmax)``, which costs a
    Python call per bar. ``np.argmax`` returns the first occurrence of the
    maximum, matching the callback it replaces; windows containing NaN are
    reported as NaN rather than silently returning the NaN's position.
    """
    n = len(values)
    result = np.full(n, np.nan, dtype=float)
    if n < window:
        return result
    windows = sliding_window_view(values, window)
    has_nan = np.isnan(windows).any(axis=1)
    index = np.argmax(windows, axis=1) if find_max else np.argmin(windows, axis=1)
    result[window - 1 :] = np.where(has_nan, np.nan, (index + 1).astype(float))
    return result


def _rolling_decay_last(values: np.ndarray, window: int) -> np.ndarray:
    """Weighted mean of each full window, newest bar weighted highest.

    Weights are 1..window applied oldest-to-newest, i.e. the newest bar carries
    weight ``window``. That is exactly a fixed-weight sum over the window, so it
    is computed as ``sum_j j * x[t - (window - j)]`` rather than calling a Python
    callback once per bar.
    """
    n = len(values)
    result = np.full(n, np.nan, dtype=float)
    if n < window:
        return result
    windows = sliding_window_view(values, window)
    has_nan = np.isnan(windows).any(axis=1)
    weights = np.arange(1, window + 1, dtype=float)
    weighted = (windows * weights).sum(axis=1) / weights.sum()
    result[window - 1 :] = np.where(has_nan, np.nan, weighted)
    return result


def _per_code_vectorised(
    df: pd.DataFrame,
    value_col: str,
    code_col: str,
    window: int,
    *,
    find_max: bool,
) -> pd.Series:
    """Apply a per-code rolling kernel without a Python call per window."""
    values = df[value_col].to_numpy(dtype=float)
    result = np.full(len(df), np.nan, dtype=float)
    for positions in df.groupby(code_col, sort=False).indices.values():
        result[positions] = _rolling_extreme_position(
            values[positions], window, find_max=find_max
        )
    return pd.Series(result, index=df.index)


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

    if min_obs != window:
        def _argmax_1based(values: np.ndarray) -> float:
            if np.isnan(values).any():
                return np.nan
            return float(np.argmax(values) + 1)

        if value_col is None:
            return df.rolling(window, min_periods=min_obs).apply(_argmax_1based, raw=True)
        return df.groupby(code_col)[str(value_col)].transform(
            lambda x: x.rolling(window, min_periods=min_obs).apply(_argmax_1based, raw=True)
        )

    if value_col is None:
        frames = {
            column: _rolling_extreme_position(df[column].to_numpy(dtype=float), window, find_max=True)
            for column in df.columns
            if pd.api.types.is_numeric_dtype(df[column])
        }
        return pd.DataFrame(frames, index=df.index)
    return _per_code_vectorised(df, str(value_col), code_col, window, find_max=True)


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

    if min_obs != window:
        def _argmin_1based(values: np.ndarray) -> float:
            if np.isnan(values).any():
                return np.nan
            return float(np.argmin(values) + 1)

        if value_col is None:
            return df.rolling(window, min_periods=min_obs).apply(_argmin_1based, raw=True)
        return df.groupby(code_col)[str(value_col)].transform(
            lambda x: x.rolling(window, min_periods=min_obs).apply(_argmin_1based, raw=True)
        )

    if value_col is None:
        frames = {
            column: _rolling_extreme_position(df[column].to_numpy(dtype=float), window, find_max=False)
            for column in df.columns
            if pd.api.types.is_numeric_dtype(df[column])
        }
        return pd.DataFrame(frames, index=df.index)
    return _per_code_vectorised(df, str(value_col), code_col, window, find_max=False)


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

    if min_obs != window:
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

    values = df[value_col].to_numpy(dtype=float)
    result = np.full(len(df), np.nan, dtype=float)
    for positions in df.groupby(code_col, sort=False).indices.values():
        result[positions] = _rolling_decay_last(values[positions], window)
    return pd.Series(result, index=df.index)


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
    amount_col: str = "total_turnover",
    volume_col: str = "volume",
    fallback_cols: tuple[str, str, str, str] = ("open", "high", "low", "close"),
    vwap_col: str = "vwap",
) -> pd.Series:
    """VWAP, preferring the panel's own column and deriving it only if absent.

    Precedence matters here. The export contract already ships a ``vwap`` column,
    so re-deriving it from a *differently named* turnover column would silently
    produce a second, disagreeing definition. And the turnover column is
    ``total_turnover`` on this panel, not ``amount``; hard-coding ``amount`` made
    every expression mentioning VWAP raise KeyError on a contract-conforming panel.
    """
    if vwap_col in df.columns:
        return df[vwap_col].astype(float)

    candidates = [amount_col, "total_turnover", "amount"]
    amount_series = next((df[c] for c in candidates if c in df.columns), None)
    if amount_series is None:
        raise KeyError(
            f"compute_vwap found no vwap column and no turnover column among {candidates}"
        )

    volume = df[volume_col]
    vwap = safe_div(amount_series.astype(float), volume.replace(0, np.nan))
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


def rolling_quantile(
    df: pd.DataFrame,
    value_col: str,
    window: int,
    q: float,
    *,
    code_col: str = "code",
    min_periods: int | None = None,
) -> pd.Series:
    """Rolling quantile at level ``q`` (linear interpolation between order stats)."""
    window = as_window(window)
    min_obs = window if min_periods is None else min_periods
    level = float(q)
    if not 0.0 <= level <= 1.0:
        raise ValueError(f"quantile level must lie in [0, 1], got {q!r}")
    return df.groupby(code_col)[value_col].transform(
        lambda x: x.rolling(window, min_periods=min_obs).quantile(level)
    )


def rolling_slope(
    df: pd.DataFrame,
    value_col: str,
    window: int,
    *,
    code_col: str = "code",
    min_periods: int | None = None,
) -> pd.Series:
    """Rolling OLS slope of the series against time ``t = 1..N``.

    Matches Qlib's ``Slope``: regress the window (in chronological order) on
    ``1, 2, ..., N`` and return the slope. NaN observations inside the window
    are dropped from the fit rather than treated as zero.
    """
    window = as_window(window)
    min_obs = window if min_periods is None else min_periods

    def _slope(values: np.ndarray) -> float:
        y = values.astype(float)
        mask = ~np.isnan(y)
        n = int(mask.sum())
        if n < 2:
            return np.nan
        x = np.arange(1, len(y) + 1, dtype=float)[mask]
        y = y[mask]
        sxx = n * np.dot(x, x) - x.sum() ** 2
        if sxx == 0:
            return np.nan
        return float((n * np.dot(x, y) - x.sum() * y.sum()) / sxx)

    return df.groupby(code_col)[value_col].transform(
        lambda x: x.rolling(window, min_periods=min_obs).apply(_slope, raw=True)
    )


def _ols_diagnostics(values: np.ndarray) -> tuple[float, float, float]:
    """Return (slope, r_squared, residual_of_last_point) for one window."""
    y = values.astype(float)
    mask = ~np.isnan(y)
    n = int(mask.sum())
    if n < 2:
        return np.nan, np.nan, np.nan
    x = np.arange(1, len(y) + 1, dtype=float)[mask]
    y = y[mask]
    sxx = n * np.dot(x, x) - x.sum() ** 2
    if sxx == 0:
        return np.nan, np.nan, np.nan
    slope = (n * np.dot(x, y) - x.sum() * y.sum()) / sxx
    intercept = y.mean() - slope * x.mean()

    # The residual is taken at the *current* bar, i.e. at t = len(window),
    # which is what Qlib's Resi returns.
    current_t = float(len(values))
    current_value = float(values[-1])
    residual = current_value - (slope * current_t + intercept)

    denom = sxx * (n * np.dot(y, y) - y.sum() ** 2)
    rsquare = np.nan if denom <= 0 else ((n * np.dot(x, y) - x.sum() * y.sum()) ** 2) / denom
    return float(slope), float(rsquare), float(residual)


def rolling_rsquare(
    df: pd.DataFrame,
    value_col: str,
    window: int,
    *,
    code_col: str = "code",
    min_periods: int | None = None,
) -> pd.Series:
    """Rolling coefficient of determination of the series against time ``t = 1..N``."""
    window = as_window(window)
    min_obs = window if min_periods is None else min_periods
    return df.groupby(code_col)[value_col].transform(
        lambda x: x.rolling(window, min_periods=min_obs).apply(
            lambda v: _ols_diagnostics(v)[1], raw=True
        )
    )


def rolling_resi(
    df: pd.DataFrame,
    value_col: str,
    window: int,
    *,
    code_col: str = "code",
    min_periods: int | None = None,
) -> pd.Series:
    """Rolling residual of the newest bar against a linear fit over the window.

    Matches Qlib's ``Resi``: fit the window on ``t = 1..N``, then return
    ``y_t - (slope * t + intercept)`` evaluated at the current bar.
    """
    window = as_window(window)
    min_obs = window if min_periods is None else min_periods
    return df.groupby(code_col)[value_col].transform(
        lambda x: x.rolling(window, min_periods=min_obs).apply(
            lambda v: _ols_diagnostics(v)[2], raw=True
        )
    )


def rolling_idxmax(
    df: pd.DataFrame,
    value_col: str,
    window: int,
    *,
    code_col: str = "code",
    min_periods: int | None = None,
) -> pd.Series:
    """1-based position of the window maximum, counted from the window start.

    Matches Qlib's ``IdxMax``, which returns ``argmax() + 1`` over the window in
    chronological order. The result therefore lies in ``[1, window]`` rather
    than being normalised.
    """
    window = as_window(window)
    min_obs = window if min_periods is None else min_periods
    return df.groupby(code_col)[value_col].transform(
        lambda x: x.rolling(window, min_periods=min_obs).apply(
            lambda v: float(np.nanargmax(v) + 1) if not np.all(np.isnan(v)) else np.nan,
            raw=True,
        )
    )


def rolling_idxmin(
    df: pd.DataFrame,
    value_col: str,
    window: int,
    *,
    code_col: str = "code",
    min_periods: int | None = None,
) -> pd.Series:
    """1-based position of the window minimum, counted from the window start."""
    window = as_window(window)
    min_obs = window if min_periods is None else min_periods
    return df.groupby(code_col)[value_col].transform(
        lambda x: x.rolling(window, min_periods=min_obs).apply(
            lambda v: float(np.nanargmin(v) + 1) if not np.all(np.isnan(v)) else np.nan,
            raw=True,
        )
    )


def ts_ema(
    df: pd.DataFrame,
    value_col: str,
    window: int,
    *,
    code_col: str = "code",
    min_periods: int | None = None,
) -> pd.Series:
    """Exponential moving average with ``span = window``.

    Follows Qlib's ``EMA``, which calls ``ewm(span=N)`` with pandas' default
    ``adjust=True``. A fractional window in ``(0, 1)`` is read as a decay
    factor, again matching Qlib.
    """
    min_obs = 1 if min_periods is None else min_periods
    raw = float(window)
    if 0.0 < raw < 1.0:
        return df.groupby(code_col)[value_col].transform(
            lambda x: x.ewm(alpha=raw, min_periods=min_obs).mean()
        )
    span = as_window(window)
    return df.groupby(code_col)[value_col].transform(
        lambda x: x.ewm(span=span, min_periods=min_obs).mean()
    )


def bollinger_band(
    df: pd.DataFrame,
    value_col: str,
    window: int,
    num_std: float = 2.0,
    *,
    code_col: str = "code",
    min_periods: int | None = None,
    upper: bool = True,
) -> pd.Series:
    """Bollinger band: moving average plus or minus ``num_std`` deviations."""
    window = as_window(window)
    min_obs = window if min_periods is None else min_periods
    k = float(num_std)

    def _band(x: pd.Series) -> pd.Series:
        mean = x.rolling(window, min_periods=min_obs).mean()
        std = x.rolling(window, min_periods=min_obs).std(ddof=0)
        return mean + k * std if upper else mean - k * std

    return df.groupby(code_col)[value_col].transform(_band)


def bollinger_band_upper(
    df: pd.DataFrame,
    value_col: str,
    window: int,
    num_std: float = 2.0,
    *,
    code_col: str = "code",
    min_periods: int | None = None,
) -> pd.Series:
    """Upper Bollinger band, bound for the expression compiler's calling shape."""
    return bollinger_band(
        df, value_col, window, num_std,
        code_col=code_col, min_periods=min_periods, upper=True,
    )


def bollinger_band_lower(
    df: pd.DataFrame,
    value_col: str,
    window: int,
    num_std: float = 2.0,
    *,
    code_col: str = "code",
    min_periods: int | None = None,
) -> pd.Series:
    """Lower Bollinger band, bound for the expression compiler's calling shape."""
    return bollinger_band(
        df, value_col, window, num_std,
        code_col=code_col, min_periods=min_periods, upper=False,
    )


def bias(
    df: pd.DataFrame,
    value_col: str,
    window: int,
    *,
    code_col: str = "code",
    min_periods: int | None = None,
) -> pd.Series:
    """BIAS: percentage deviation of the value from its moving average."""
    window = as_window(window)
    min_obs = window if min_periods is None else min_periods

    def _bias(x: pd.Series) -> pd.Series:
        mean = x.rolling(window, min_periods=min_obs).mean()
        return (x - mean) / mean.replace(0, np.nan) * 100.0

    return df.groupby(code_col)[value_col].transform(_bias)


def true_range(
    df: pd.DataFrame,
    close_col: str,
    high_col: str,
    low_col: str,
    window: int,
    *,
    code_col: str = "code",
    min_periods: int | None = None,
) -> pd.Series:
    """Average True Range over ``window`` bars.

    True range is the greatest of the bar's own range and its gaps from the
    previous close; the passed ``close_col`` supplies that previous close.
    """
    window = as_window(window)
    min_obs = window if min_periods is None else min_periods
    previous_close = df.groupby(code_col)[close_col].shift(1)
    high = df[high_col]
    low = df[low_col]
    tr = pd.concat(
        [
            (high - low).abs(),
            (high - previous_close).abs(),
            (low - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    working = df.assign(_true_range=tr)
    return working.groupby(code_col)["_true_range"].transform(
        lambda x: x.rolling(window, min_periods=min_obs).mean()
    )


def commodity_channel_index(
    df: pd.DataFrame,
    close_col: str,
    high_col: str,
    low_col: str,
    window: int,
    *,
    code_col: str = "code",
    min_periods: int | None = None,
) -> pd.Series:
    """Commodity Channel Index: deviation of typical price from its own mean."""
    window = as_window(window)
    min_obs = window if min_periods is None else min_periods
    typical = (df[high_col] + df[low_col] + df[close_col]) / 3.0
    working = df.assign(_typical=typical)

    def _cci(x: pd.Series) -> pd.Series:
        mean = x.rolling(window, min_periods=min_obs).mean()
        mad = x.rolling(window, min_periods=min_obs).apply(
            lambda v: np.nanmean(np.abs(v - np.nanmean(v))), raw=True
        )
        return (x - mean) / (0.015 * mad.replace(0, np.nan))

    return working.groupby(code_col)["_typical"].transform(_cci)


def relative_strength_index(
    df: pd.DataFrame,
    value_col: str,
    window: int,
    *,
    code_col: str = "code",
    min_periods: int | None = None,
) -> pd.Series:
    """Relative Strength Index over ``window`` bars, scaled to 0-100."""
    window = as_window(window)
    min_obs = window if min_periods is None else min_periods
    change = df.groupby(code_col)[value_col].diff()
    gain = change.clip(lower=0.0)
    loss = (-change).clip(lower=0.0)
    working = df.assign(_gain=gain, _loss=loss)

    def _rsi(x: pd.Series) -> pd.Series:
        group = working.loc[x.index]
        avg_gain = group["_gain"].rolling(window, min_periods=min_obs).mean()
        avg_loss = group["_loss"].rolling(window, min_periods=min_obs).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100.0 - 100.0 / (1.0 + rs)
        # All-gain windows have zero average loss and RSI 100 by definition.
        return rsi.where(avg_loss != 0, 100.0).where(avg_gain.notna())

    return working.groupby(code_col)[value_col].transform(lambda x: _rsi(x))


def rolling_variance(
    df: pd.DataFrame,
    value_col: str,
    window: int,
    *,
    code_col: str = "code",
    min_periods: int | None = None,
) -> pd.Series:
    """Rolling population variance (``ddof=0``)."""
    window = as_window(window)
    min_obs = window if min_periods is None else min_periods
    return df.groupby(code_col)[value_col].transform(
        lambda x: x.rolling(window, min_periods=min_obs).var(ddof=0)
    )


def rolling_skewness(
    df: pd.DataFrame,
    value_col: str,
    window: int,
    *,
    code_col: str = "code",
    min_periods: int | None = None,
) -> pd.Series:
    """Rolling sample skewness (Fisher-Pearson, ``bias=False``)."""
    window = as_window(window)
    min_obs = window if min_periods is None else min_periods
    return df.groupby(code_col)[value_col].transform(
        lambda x: x.rolling(window, min_periods=min_obs).skew()
    )


def rolling_kurtosis(
    df: pd.DataFrame,
    value_col: str,
    window: int,
    *,
    code_col: str = "code",
    min_periods: int | None = None,
) -> pd.Series:
    """Rolling sample excess kurtosis (Fisher, ``bias=False``)."""
    window = as_window(window)
    min_obs = window if min_periods is None else min_periods
    return df.groupby(code_col)[value_col].transform(
        lambda x: x.rolling(window, min_periods=min_obs).kurt()
    )


def rolling_sharpe_ratio(
    df: pd.DataFrame,
    value_col: str,
    window: int,
    *,
    code_col: str = "code",
    min_periods: int | None = None,
) -> pd.Series:
    """Rolling mean over rolling standard deviation of simple returns.

    Sharpe ratio 通达信公式：``SHARPERATIO = MA(CLOSE/N, N) / STD(CLOSE/N, N)`` where
    ``CLOSE/N`` is the simple return series, so this operates on returns and
    returns NaN where the local volatility is zero rather than dividing by it.
    """
    window = as_window(window)
    min_obs = window if min_periods is None else min_periods
    returns = df.groupby(code_col)[value_col].pct_change()
    working = df.assign(_sharpe_returns=returns)

    def _ratio(x: pd.Series) -> pd.Series:
        mean = x.rolling(window, min_periods=min_obs).mean()
        std = x.rolling(window, min_periods=min_obs).std(ddof=1)
        return mean / std.replace(0, np.nan)

    return working.groupby(code_col)["_sharpe_returns"].transform(_ratio)


def psychological_line(
    df: pd.DataFrame,
    value_col: str,
    window: int,
    *,
    code_col: str = "code",
    min_periods: int | None = None,
) -> pd.Series:
    """PSY: percentage of bars in the window that closed up.

    通达信公式：``PSY = COUNT(CLOSE > REF(CLOSE,1), N) / N * 100``
    """
    window = as_window(window)
    min_obs = window if min_periods is None else min_periods
    up = (df.groupby(code_col)[value_col].diff() > 0).astype(float)
    working = df.assign(_psy_up=up)
    return (
        working.groupby(code_col)["_psy_up"]
        .transform(lambda x: x.rolling(window, min_periods=min_obs).mean())
        * 100.0
    )


def triple_exponential_rate(
    df: pd.DataFrame,
    value_col: str,
    window: int,
    *,
    code_col: str = "code",
    min_periods: int | None = None,
) -> pd.Series:
    """TRIX: percentage rate of change of a triply smoothed EMA.

    通达信公式：``TR = EMA(EMA(EMA(CLOSE,N),N),N); TRIX = (TR - REF(TR,1)) / REF(TR,1) * 100``
    """
    window = as_window(window)
    min_obs = window if min_periods is None else min_periods

    def _trix(x: pd.Series) -> pd.Series:
        smoothed = x
        for _ in range(3):
            smoothed = smoothed.ewm(span=window, min_periods=min_obs).mean()
        previous = smoothed.shift(1)
        return (smoothed - previous) / previous.replace(0, np.nan) * 100.0

    return df.groupby(code_col)[value_col].transform(_trix)


def bull_bear_index(
    df: pd.DataFrame,
    value_col: str,
    short: int,
    mid: int,
    long: int,
    longer: int,
    *,
    code_col: str = "code",
    min_periods: int | None = None,
) -> pd.Series:
    """BBI: the average of four moving averages.

    通达信公式：``BBI = (MA(CLOSE,3) + MA(CLOSE,6) + MA(CLOSE,12) + MA(CLOSE,24)) / 4``
    Each average uses the full window (``min_periods`` defaults to the window).
    """
    spans = [as_window(short), as_window(mid), as_window(long), as_window(longer)]

    def _bbi(x: pd.Series) -> pd.Series:
        total = None
        for span in spans:
            obs = span if min_periods is None else min_periods
            average = x.rolling(span, min_periods=obs).mean()
            total = average if total is None else total + average
        return total / len(spans)

    return df.groupby(code_col)[value_col].transform(_bbi)


def _previous(df: pd.DataFrame, column: str, code_col: str) -> pd.Series:
    return df.groupby(code_col)[column].shift(1)


def money_flow_index(
    df: pd.DataFrame,
    close_col: str,
    high_col: str,
    low_col: str,
    volume_col: str,
    window: int,
    *,
    code_col: str = "code",
    min_periods: int | None = None,
) -> pd.Series:
    """MFI: volume-weighted RSI on typical price.

    ``TP = (H + L + C) / 3``; money flow is ``TP * VOL``, split into positive and
    negative by whether ``TP`` rose or fell against the previous bar. Standard
    definition, 通达信 ``MFI``.
    """
    window = as_window(window)
    min_obs = window if min_periods is None else min_periods
    typical = (df[high_col] + df[low_col] + df[close_col]) / 3.0
    flow = typical * df[volume_col]
    change = typical - _previous(df.assign(_tp=typical), "_tp", code_col)
    positive = flow.where(change > 0, 0.0)
    negative = flow.where(change < 0, 0.0)
    working = df.assign(_mfi_pos=positive, _mfi_neg=negative)

    def _mfi(x: pd.Series) -> pd.Series:
        group = working.loc[x.index]
        up = group["_mfi_pos"].rolling(window, min_periods=min_obs).sum()
        down = group["_mfi_neg"].rolling(window, min_periods=min_obs).sum()
        ratio = up / down.replace(0, np.nan)
        value = 100.0 - 100.0 / (1.0 + ratio)
        # With no negative flow in the window the index saturates at 100.
        return value.where(down != 0, 100.0).where(up.notna())

    return working.groupby(code_col)[close_col].transform(_mfi)


def volume_ratio(
    df: pd.DataFrame,
    close_col: str,
    volume_col: str,
    window: int,
    *,
    code_col: str = "code",
    min_periods: int | None = None,
) -> pd.Series:
    """VR: up-volume over down-volume, in percent.

    通达信公式：``VR = SUM(VOL, up bars) / SUM(VOL, down bars) * 100`` where a bar
    counts as up when its close rose against the previous close. Flat bars are
    counted in neither sum.
    """
    window = as_window(window)
    min_obs = window if min_periods is None else min_periods
    change = df.groupby(code_col)[close_col].diff()
    up = df[volume_col].where(change > 0, 0.0)
    down = df[volume_col].where(change < 0, 0.0)
    working = df.assign(_vr_up=up, _vr_down=down)

    def _vr(x: pd.Series) -> pd.Series:
        group = working.loc[x.index]
        up_sum = group["_vr_up"].rolling(window, min_periods=min_obs).sum()
        down_sum = group["_vr_down"].rolling(window, min_periods=min_obs).sum()
        return up_sum / down_sum.replace(0, np.nan) * 100.0

    return working.groupby(code_col)[close_col].transform(_vr)


def capability_ratio(
    df: pd.DataFrame,
    close_col: str,
    high_col: str,
    low_col: str,
    window: int,
    *,
    code_col: str = "code",
    min_periods: int | None = None,
) -> pd.Series:
    """CR: willingness to buy against willingness to sell, around the mid price.

    ``MID = (H + L + C) / 3`` on the *previous* bar, then
    ``CR = SUM(MAX(0, H - MID), N) / SUM(MAX(0, MID - L), N) * 100``.
    通达信 ``CR`` 公式口径。
    """
    window = as_window(window)
    min_obs = window if min_periods is None else min_periods
    mid = ((df[high_col] + df[low_col] + df[close_col]) / 3.0).groupby(df[code_col]).shift(1)
    upward = (df[high_col] - mid).clip(lower=0.0)
    downward = (mid - df[low_col]).clip(lower=0.0)
    working = df.assign(_cr_up=upward, _cr_down=downward)

    def _cr(x: pd.Series) -> pd.Series:
        group = working.loc[x.index]
        up_sum = group["_cr_up"].rolling(window, min_periods=min_obs).sum()
        down_sum = group["_cr_down"].rolling(window, min_periods=min_obs).sum()
        return up_sum / down_sum.replace(0, np.nan) * 100.0

    return working.groupby(code_col)[close_col].transform(_cr)


def popularity_index(
    df: pd.DataFrame,
    open_col: str,
    close_col: str,
    high_col: str,
    low_col: str,
    window: int,
    *,
    code_col: str = "code",
    min_periods: int | None = None,
) -> pd.Series:
    """AR: intraday strength of the open, in percent.

    通达信公式：``AR = SUM(HIGH - OPEN, N) / SUM(OPEN - LOW, N) * 100``
    """
    window = as_window(window)
    min_obs = window if min_periods is None else min_periods
    upward = df[high_col] - df[open_col]
    downward = df[open_col] - df[low_col]
    working = df.assign(_ar_up=upward, _ar_down=downward)

    def _ar(x: pd.Series) -> pd.Series:
        group = working.loc[x.index]
        up_sum = group["_ar_up"].rolling(window, min_periods=min_obs).sum()
        down_sum = group["_ar_down"].rolling(window, min_periods=min_obs).sum()
        return up_sum / down_sum.replace(0, np.nan) * 100.0

    return working.groupby(code_col)[close_col].transform(_ar)


def willingness_index(
    df: pd.DataFrame,
    open_col: str,
    close_col: str,
    high_col: str,
    low_col: str,
    window: int,
    *,
    code_col: str = "code",
    min_periods: int | None = None,
) -> pd.Series:
    """BR: willingness to trade away from the previous close, in percent.

    通达信公式：
    ``BR = SUM(MAX(0, HIGH - REF(CLOSE,1)), N) / SUM(MAX(0, REF(CLOSE,1) - LOW), N) * 100``
    """
    window = as_window(window)
    min_obs = window if min_periods is None else min_periods
    previous_close = _previous(df, close_col, code_col)
    upward = (df[high_col] - previous_close).clip(lower=0.0)
    downward = (previous_close - df[low_col]).clip(lower=0.0)
    working = df.assign(_br_up=upward, _br_down=downward)

    def _br(x: pd.Series) -> pd.Series:
        group = working.loc[x.index]
        up_sum = group["_br_up"].rolling(window, min_periods=min_obs).sum()
        down_sum = group["_br_down"].rolling(window, min_periods=min_obs).sum()
        return up_sum / down_sum.replace(0, np.nan) * 100.0

    return working.groupby(code_col)[close_col].transform(_br)


def compute_returns(
    df: pd.DataFrame,
    *,
    close_col: str = "close",
    code_col: str = "code",
) -> pd.Series:
    """Simple daily return per code, for the catalog's ``returns``/``daily_return``.

    Derived from the panel's own close, so it carries whatever adjustment basis
    the panel declares. Dividing by an adjusted close is correct precisely because
    both ends of the ratio are adjusted.
    """
    if close_col not in df.columns:
        raise KeyError(f"compute_returns needs a {close_col!r} column")
    return df.groupby(code_col)[close_col].pct_change()


def compute_adv(
    df: pd.DataFrame,
    window: int,
    *,
    turnover_col: str = "total_turnover",
    price_col: str = "close",
    volume_col: str = "volume",
    code_col: str = "code",
    min_periods: int | None = None,
) -> pd.Series:
    """Average daily dollar volume over ``window`` bars, as WorldQuant's ``advN``.

    Dollar volume is taken from ``total_turnover`` (成交额), which *is* the traded
    cash amount. The tempting ``close * volume`` is wrong here because the panel's
    close is post-adjusted: multiplying an adjusted price by an unadjusted share
    count gives a number that is neither the traded amount nor a clean ratio.
    ``close * volume`` is used only when no turnover column is present, and the
    caller should treat that as a degraded substitute.
    """
    window = as_window(window)
    min_obs = window if min_periods is None else min_periods

    if turnover_col in df.columns:
        dollars = df[turnover_col].astype(float)
    elif price_col in df.columns and volume_col in df.columns:
        dollars = df[price_col].astype(float) * df[volume_col].astype(float)
    else:
        raise KeyError(
            f"compute_adv needs either {turnover_col!r} or both {price_col!r} and {volume_col!r}"
        )

    working = df.assign(_adv_dollars=dollars)
    return working.groupby(code_col)["_adv_dollars"].transform(
        lambda x: x.rolling(window, min_periods=min_obs).mean()
    )


__all__ = [
    "SequenceSpec",
    "align_sort",
    "as_window",
    "bias",
    "bollinger_band",
    "bollinger_band_lower",
    "bollinger_band_upper",
    "bull_bear_index",
    "capability_ratio",
    "commodity_channel_index",
    "compute_adv",
    "compute_returns",
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
    "money_flow_index",
    "panel_to_wide",
    "popularity_index",
    "psychological_line",
    "returns_from_close",
    "relative_strength_index",
    "rolling_corr",
    "rolling_count",
    "rolling_cov",
    "rolling_idxmax",
    "rolling_idxmin",
    "rolling_kurtosis",
    "rolling_max",
    "rolling_mean",
    "rolling_min",
    "rolling_product",
    "rolling_quantile",
    "rolling_regression_beta",
    "rolling_regression_residual",
    "rolling_resi",
    "rolling_rsquare",
    "rolling_sharpe_ratio",
    "rolling_skewness",
    "rolling_slope",
    "rolling_std",
    "rolling_sum",
    "rolling_sumif",
    "rolling_variance",
    "safe_div",
    "signed_power",
    "sma",
    "sort_panel",
    "sumac",
    "time_series_rank",
    "triple_exponential_rate",
    "true_range",
    "ts_argmax",
    "ts_argmin",
    "ts_decay_linear",
    "ts_delay",
    "ts_delta",
    "ts_ema",
    "ts_max",
    "ts_mean",
    "ts_min",
    "ts_product",
    "ts_rank",
    "ts_std",
    "ts_sum",
    "volume_ratio",
    "willingness_index",
    "wma",
]
