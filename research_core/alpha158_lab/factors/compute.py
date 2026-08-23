from __future__ import annotations

import numpy as np
import pandas as pd

from research_core.alpha158_lab.factors.specs import ALPHA158_FIRST_10

_ROLLING_WINDOWS = (5, 10, 20, 30, 60)
_SLOPE_X: dict[int, tuple[np.ndarray, float, float]] = {}


def _safe_div(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    denom = denominator.replace(0, np.nan)
    return numerator / denom


def _slope_constants(window: int) -> tuple[np.ndarray, float, float]:
    cached = _SLOPE_X.get(window)
    if cached is not None:
        return cached
    x = np.arange(1, window + 1, dtype=np.float64)
    x_mean = x.mean()
    x_var = float(((x - x_mean) ** 2).sum())
    cached = (x, x_mean, x_var)
    _SLOPE_X[window] = cached
    return cached


def _rolling_slope(series: pd.Series, window: int) -> pd.Series:
    x, x_mean, x_var = _slope_constants(window)

    def _calc(values: np.ndarray) -> float:
        if np.isnan(values).any():
            return np.nan
        y_mean = values.mean()
        cov = ((x - x_mean) * (values - y_mean)).sum()
        return float(cov / x_var)

    return series.rolling(window, min_periods=window).apply(_calc, raw=True)


def _rolling_rsquare(series: pd.Series, window: int) -> pd.Series:
    x, x_mean, x_var = _slope_constants(window)
    x_std = float(np.sqrt(x_var))
    x_demean = x - x_mean

    def _calc(values: np.ndarray) -> float:
        if np.isnan(values).any():
            return np.nan
        y_demean = values - values.mean()
        y_var = (y_demean ** 2).sum()
        if y_var == 0:
            return np.nan
        cov = (x_demean * y_demean).sum()
        corr = cov / (x_std * np.sqrt(y_var))
        return float(corr * corr)

    return series.rolling(window, min_periods=window).apply(_calc, raw=True)


def _rolling_idxmax(series: pd.Series, window: int) -> pd.Series:
    def _calc(values: np.ndarray) -> float:
        if np.isnan(values).any():
            return np.nan
        return float(values.argmax() + 1)

    return series.rolling(window, min_periods=1).apply(_calc, raw=True) / window


def _rolling_idxmin(series: pd.Series, window: int) -> pd.Series:
    def _calc(values: np.ndarray) -> float:
        if np.isnan(values).any():
            return np.nan
        return float(values.argmin() + 1)

    return series.rolling(window, min_periods=1).apply(_calc, raw=True) / window


def _rolling_corr(left: pd.Series, right: pd.Series, window: int) -> pd.Series:
    corr = left.rolling(window, min_periods=1).corr(right)
    left_std = left.rolling(window, min_periods=1).std()
    right_std = right.rolling(window, min_periods=1).std()
    corr[(left_std.abs() < 2e-5) | (right_std.abs() < 2e-5)] = np.nan
    return corr


def _rolling_resi(series: pd.Series, window: int) -> pd.Series:
    x, x_mean, x_var = _slope_constants(window)

    def _calc(values: np.ndarray) -> float:
        if np.isnan(values).any():
            return np.nan
        y_current = values[-1]
        y_mean = values.mean()
        slope = ((x - x_mean) * (values - y_mean)).sum() / x_var
        intercept = y_mean - slope * x_mean
        fitted = slope * window + intercept
        return float(y_current - fitted)

    return series.rolling(window, min_periods=window).apply(_calc, raw=True)


def _needs(names: set[str] | None, *candidates: str) -> bool:
    return names is None or any(name in names for name in candidates)


def _build_factor_values(data: pd.DataFrame, factor_names: set[str] | None = None) -> dict[str, pd.Series]:
    open_ = data["open"]
    high = data["high"]
    low = data["low"]
    close = data["close"]
    vwap = data["vwap"]
    body = close - open_
    span = high - low
    upper_shadow = high - np.maximum(open_, close)
    lower_shadow = np.minimum(open_, close) - low

    grouped_close = data.groupby("code")["close"]
    grouped_high = data.groupby("code")["high"]
    grouped_low = data.groupby("code")["low"]
    grouped_volume = data.groupby("code")["volume"]
    prev_close = grouped_close.shift(1)
    price_change = close - prev_close
    up_flag = (close > prev_close).astype(float)
    down_flag = (close < prev_close).astype(float)
    gain = price_change.clip(lower=0)
    loss = (-price_change).clip(lower=0)
    abs_change = price_change.abs()
    volume = data["volume"]
    prev_volume = grouped_volume.shift(1)
    volume_change = volume - prev_volume
    volume_gain = volume_change.clip(lower=0)
    volume_loss = (-volume_change).clip(lower=0)
    volume_abs_change = volume_change.abs()
    wvma_base = (close / prev_close - 1).abs() * volume
    grouped_wvma_base = wvma_base.groupby(data["code"])
    values: dict[str, pd.Series] = {}
    kbar_map = {
        "KMID": _safe_div(body, open_),
        "KLEN": _safe_div(span, open_),
        "KMID2": _safe_div(body, span + 1e-12),
        "KUP": _safe_div(upper_shadow, open_),
        "KUP2": _safe_div(upper_shadow, span + 1e-12),
        "KLOW": _safe_div(lower_shadow, open_),
        "KLOW2": _safe_div(lower_shadow, span + 1e-12),
        "KSFT": _safe_div(2 * close - high - low, open_),
        "KSFT2": _safe_div(2 * close - high - low, span + 1e-12),
        "OPEN0": _safe_div(open_, close),
        "HIGH0": _safe_div(high, close),
        "LOW0": _safe_div(low, close),
        "VWAP0": _safe_div(vwap, close),
    }
    for name, series in kbar_map.items():
        if _needs(factor_names, name):
            values[name] = series

    for window in _ROLLING_WINDOWS:
        if _needs(factor_names, f"ROC{window}"):
            values[f"ROC{window}"] = _safe_div(grouped_close.shift(window), close)
        if _needs(factor_names, f"MA{window}"):
            rolling_mean = grouped_close.transform(
                lambda series, w=window: series.rolling(w, min_periods=w).mean()
            )
            values[f"MA{window}"] = _safe_div(rolling_mean, close)
        if _needs(factor_names, f"STD{window}"):
            rolling_std = grouped_close.transform(
                lambda series, w=window: series.rolling(w, min_periods=w).std(ddof=0)
            )
            values[f"STD{window}"] = _safe_div(rolling_std, close)
        if _needs(factor_names, f"BETA{window}"):
            rolling_slope = grouped_close.transform(lambda series, w=window: _rolling_slope(series, w))
            values[f"BETA{window}"] = _safe_div(rolling_slope, close)
        if _needs(factor_names, f"RSQR{window}"):
            values[f"RSQR{window}"] = grouped_close.transform(
                lambda series, w=window: _rolling_rsquare(series, w)
            )
        if _needs(factor_names, f"RESI{window}"):
            rolling_resi = grouped_close.transform(lambda series, w=window: _rolling_resi(series, w))
            values[f"RESI{window}"] = _safe_div(rolling_resi, close)
        if _needs(factor_names, f"MAX{window}"):
            rolling_max = grouped_high.transform(
                lambda series, w=window: series.rolling(w, min_periods=w).max()
            )
            values[f"MAX{window}"] = _safe_div(rolling_max, close)
        if _needs(factor_names, f"MIN{window}"):
            rolling_min = grouped_low.transform(
                lambda series, w=window: series.rolling(w, min_periods=w).min()
            )
            values[f"MIN{window}"] = _safe_div(rolling_min, close)
        if _needs(factor_names, f"QTLU{window}"):
            rolling_qtlu = grouped_close.transform(
                lambda series, w=window: series.rolling(w, min_periods=1).quantile(0.8)
            )
            values[f"QTLU{window}"] = _safe_div(rolling_qtlu, close)
        if _needs(factor_names, f"QTLD{window}"):
            rolling_qtld = grouped_close.transform(
                lambda series, w=window: series.rolling(w, min_periods=1).quantile(0.2)
            )
            values[f"QTLD{window}"] = _safe_div(rolling_qtld, close)
        if _needs(factor_names, f"RANK{window}"):
            rolling_rank = grouped_close.transform(
                lambda series, w=window: series.rolling(w, min_periods=1).rank(pct=True)
            )
            values[f"RANK{window}"] = rolling_rank
        if _needs(factor_names, f"RSV{window}"):
            rolling_min_low = grouped_low.transform(
                lambda series, w=window: series.rolling(w, min_periods=1).min()
            )
            rolling_max_high = grouped_high.transform(
                lambda series, w=window: series.rolling(w, min_periods=1).max()
            )
            values[f"RSV{window}"] = _safe_div(
                close - rolling_min_low,
                rolling_max_high - rolling_min_low + 1e-12,
            )
        if _needs(factor_names, f"IMAX{window}"):
            values[f"IMAX{window}"] = grouped_high.transform(
                lambda series, w=window: _rolling_idxmax(series, w)
            )
        if _needs(factor_names, f"IMIN{window}"):
            values[f"IMIN{window}"] = grouped_low.transform(
                lambda series, w=window: _rolling_idxmin(series, w)
            )
        if _needs(factor_names, f"IMXD{window}"):
            imax = grouped_high.transform(lambda series, w=window: _rolling_idxmax(series, w))
            imin = grouped_low.transform(lambda series, w=window: _rolling_idxmin(series, w))
            values[f"IMXD{window}"] = imax - imin
        if _needs(factor_names, f"CORR{window}"):
            values[f"CORR{window}"] = data.groupby("code").apply(
                lambda group, w=window: _rolling_corr(
                    group["close"].astype(float),
                    np.log(group["volume"].astype(float).replace(0, np.nan) + 1.0),
                    w,
                ),
            ).reset_index(level=0, drop=True)
        if _needs(factor_names, f"CORD{window}"):
            values[f"CORD{window}"] = data.groupby("code").apply(
                lambda group, w=window: _rolling_corr(
                    group["close"].astype(float) / group["close"].astype(float).shift(1),
                    np.log(
                        (group["volume"].astype(float) / group["volume"].astype(float).shift(1)).replace(0, np.nan)
                        + 1.0
                    ),
                    w,
                ),
            ).reset_index(level=0, drop=True)
        if _needs(factor_names, f"CNTP{window}"):
            values[f"CNTP{window}"] = up_flag.groupby(data["code"]).transform(
                lambda series, w=window: series.rolling(w, min_periods=1).mean()
            )
        if _needs(factor_names, f"CNTN{window}"):
            values[f"CNTN{window}"] = down_flag.groupby(data["code"]).transform(
                lambda series, w=window: series.rolling(w, min_periods=1).mean()
            )
        if _needs(factor_names, f"CNTD{window}"):
            cntp = up_flag.groupby(data["code"]).transform(
                lambda series, w=window: series.rolling(w, min_periods=1).mean()
            )
            cntn = down_flag.groupby(data["code"]).transform(
                lambda series, w=window: series.rolling(w, min_periods=1).mean()
            )
            values[f"CNTD{window}"] = cntp - cntn
        if _needs(factor_names, f"SUMP{window}"):
            rolling_gain = gain.groupby(data["code"]).transform(
                lambda series, w=window: series.rolling(w, min_periods=1).sum()
            )
            rolling_abs = abs_change.groupby(data["code"]).transform(
                lambda series, w=window: series.rolling(w, min_periods=1).sum()
            )
            values[f"SUMP{window}"] = _safe_div(rolling_gain, rolling_abs + 1e-12)
        if _needs(factor_names, f"SUMN{window}"):
            rolling_loss = loss.groupby(data["code"]).transform(
                lambda series, w=window: series.rolling(w, min_periods=1).sum()
            )
            rolling_abs = abs_change.groupby(data["code"]).transform(
                lambda series, w=window: series.rolling(w, min_periods=1).sum()
            )
            values[f"SUMN{window}"] = _safe_div(rolling_loss, rolling_abs + 1e-12)
        if _needs(factor_names, f"SUMD{window}"):
            rolling_gain = gain.groupby(data["code"]).transform(
                lambda series, w=window: series.rolling(w, min_periods=1).sum()
            )
            rolling_loss = loss.groupby(data["code"]).transform(
                lambda series, w=window: series.rolling(w, min_periods=1).sum()
            )
            rolling_abs = abs_change.groupby(data["code"]).transform(
                lambda series, w=window: series.rolling(w, min_periods=1).sum()
            )
            values[f"SUMD{window}"] = _safe_div(rolling_gain - rolling_loss, rolling_abs + 1e-12)
        if _needs(factor_names, f"VMA{window}"):
            rolling_volume_mean = grouped_volume.transform(
                lambda series, w=window: series.rolling(w, min_periods=1).mean()
            )
            values[f"VMA{window}"] = _safe_div(rolling_volume_mean, volume + 1e-12)
        if _needs(factor_names, f"VSTD{window}"):
            rolling_volume_std = grouped_volume.transform(
                lambda series, w=window: series.rolling(w, min_periods=1).std(ddof=0)
            )
            values[f"VSTD{window}"] = _safe_div(rolling_volume_std, volume + 1e-12)
        if _needs(factor_names, f"WVMA{window}"):
            rolling_wvma_std = grouped_wvma_base.transform(
                lambda series, w=window: series.rolling(w, min_periods=1).std(ddof=0)
            )
            rolling_wvma_mean = grouped_wvma_base.transform(
                lambda series, w=window: series.rolling(w, min_periods=1).mean()
            )
            values[f"WVMA{window}"] = _safe_div(rolling_wvma_std, rolling_wvma_mean + 1e-12)
        if _needs(factor_names, f"VSUMP{window}"):
            rolling_volume_gain = volume_gain.groupby(data["code"]).transform(
                lambda series, w=window: series.rolling(w, min_periods=1).sum()
            )
            rolling_volume_abs = volume_abs_change.groupby(data["code"]).transform(
                lambda series, w=window: series.rolling(w, min_periods=1).sum()
            )
            values[f"VSUMP{window}"] = _safe_div(rolling_volume_gain, rolling_volume_abs + 1e-12)
        if _needs(factor_names, f"VSUMN{window}"):
            rolling_volume_loss = volume_loss.groupby(data["code"]).transform(
                lambda series, w=window: series.rolling(w, min_periods=1).sum()
            )
            rolling_volume_abs = volume_abs_change.groupby(data["code"]).transform(
                lambda series, w=window: series.rolling(w, min_periods=1).sum()
            )
            values[f"VSUMN{window}"] = _safe_div(rolling_volume_loss, rolling_volume_abs + 1e-12)
        if _needs(factor_names, f"VSUMD{window}"):
            rolling_volume_gain = volume_gain.groupby(data["code"]).transform(
                lambda series, w=window: series.rolling(w, min_periods=1).sum()
            )
            rolling_volume_loss = volume_loss.groupby(data["code"]).transform(
                lambda series, w=window: series.rolling(w, min_periods=1).sum()
            )
            rolling_volume_abs = volume_abs_change.groupby(data["code"]).transform(
                lambda series, w=window: series.rolling(w, min_periods=1).sum()
            )
            values[f"VSUMD{window}"] = _safe_div(
                rolling_volume_gain - rolling_volume_loss,
                rolling_volume_abs + 1e-12,
            )

    return values


def _ensure_panel_columns(panel: pd.DataFrame) -> pd.DataFrame:
    data = panel.sort_values(["code", "date"]).copy()
    if "vwap" not in data.columns and {"amount", "volume"}.issubset(data.columns):
        data["vwap"] = data["amount"] / data["volume"].replace(0, np.nan)
    return data


def compute_alpha158_factors(
    panel: pd.DataFrame,
    factor_names: list[str] | None = None,
) -> pd.DataFrame:
    """Compute requested Alpha158 factors on a SmartData/qlib-aligned panel."""
    names = list(factor_names or ALPHA158_FIRST_10)
    data = _ensure_panel_columns(panel)
    if "vwap" not in data.columns:
        raise KeyError("panel must include 'vwap' or both 'amount' and 'volume'")
    values = _build_factor_values(data, factor_names=set(names))

    missing = [name for name in names if name not in values]
    if missing:
        raise ValueError(f"Unsupported Alpha158 factors: {missing}")

    result = data[["date", "code"]].copy()
    for name in names:
        result[name] = values[name]
    return result