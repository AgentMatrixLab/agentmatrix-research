from __future__ import annotations

import numpy as np
import pandas as pd

from research_core.factor_lab.operators import safe_div, sort_panel


IMPLEMENTED_QUANT_API_33_FACTORS = (
    "ret_1m",
    "ret_3m",
    "ret_6m",
    "ret_12m",
    "volatility_1m",
    "volatility_3m",
    "reversal",
    "momentum_12_1",
    "avg_amount_1m",
    "log_amount_1m",
    "max_ret_1m",
    "min_ret_1m",
    "up_ratio_1m",
    "ma_signal",
    "vol_convergence",
    "illiquidity",
    "log_price",
    "turnover_proxy",
    "volatility_6m",
    "volume_ratio",
    "high_low_1m",
    "rsi_14",
    "bb_position",
    "ret_3m_vol_adj",
    "amplitude_1m",
    "roe_ttm",
    "roa_ttm",
    "net_margin",
    "debt_to_asset",
    "revenue_yoy",
    "profit_yoy",
    "eps_yoy",
    "asset_turnover",
)

TRADING_DAYS = {
    "1m": 21,
    "3m": 63,
    "6m": 126,
    "12m": 252,
}


def compute_quant_api_33_factors(
    df: pd.DataFrame,
    *,
    factor_names: list[str] | None = None,
) -> pd.DataFrame:
    data = _prepare_panel(df)
    requested = list(factor_names or IMPLEMENTED_QUANT_API_33_FACTORS)
    invalid = [name for name in requested if name not in FACTOR_FUNCTIONS]
    if invalid:
        raise ValueError(f"Unsupported Quant API 33 factors: {invalid}")

    payload: dict[str, pd.Series] = {}
    for factor_name in requested:
        payload[factor_name] = FACTOR_FUNCTIONS[factor_name](data).replace([np.inf, -np.inf], np.nan)
    return pd.concat([data[["date", "code"]].copy(), pd.DataFrame(payload, index=data.index)], axis=1)


def _prepare_panel(df: pd.DataFrame) -> pd.DataFrame:
    data = df.copy()
    if "code" not in data.columns and "symbol" in data.columns:
        data = data.rename(columns={"symbol": "code"})
    if "date" not in data.columns and "trade_date" in data.columns:
        data = data.rename(columns={"trade_date": "date"})

    required = {"date", "code", "open", "high", "low", "close", "volume", "amount"}
    missing = sorted(required - set(data.columns))
    if missing:
        raise ValueError(f"Missing required columns for Quant API 33 computation: {missing}")

    for column in ["open", "high", "low", "close", "volume", "amount", *FINANCIAL_COLUMNS]:
        if column in data.columns:
            data[column] = pd.to_numeric(data[column], errors="coerce")
    return sort_panel(data)


def _returns(data: pd.DataFrame) -> pd.Series:
    return data.groupby("code")["close"].pct_change(fill_method=None)


def _pct_change(data: pd.DataFrame, periods: int) -> pd.Series:
    return data.groupby("code")["close"].pct_change(periods=periods, fill_method=None)


def _rolling(data: pd.DataFrame, series: pd.Series, window: int, method: str) -> pd.Series:
    grouped = series.groupby(data["code"], sort=False)
    if method == "mean":
        return grouped.transform(lambda item: item.rolling(window, min_periods=window).mean())
    if method == "std":
        return grouped.transform(lambda item: item.rolling(window, min_periods=window).std(ddof=0))
    if method == "max":
        return grouped.transform(lambda item: item.rolling(window, min_periods=window).max())
    if method == "min":
        return grouped.transform(lambda item: item.rolling(window, min_periods=window).min())
    if method == "sum":
        return grouped.transform(lambda item: item.rolling(window, min_periods=window).sum())
    raise ValueError(f"Unsupported rolling method: {method}")


def _ret_1m(data: pd.DataFrame) -> pd.Series:
    return _pct_change(data, TRADING_DAYS["1m"])


def _ret_3m(data: pd.DataFrame) -> pd.Series:
    return _pct_change(data, TRADING_DAYS["3m"])


def _ret_6m(data: pd.DataFrame) -> pd.Series:
    return _pct_change(data, TRADING_DAYS["6m"])


def _ret_12m(data: pd.DataFrame) -> pd.Series:
    return _pct_change(data, TRADING_DAYS["12m"])


def _volatility_1m(data: pd.DataFrame) -> pd.Series:
    return _rolling(data, _returns(data), TRADING_DAYS["1m"], "std")


def _volatility_3m(data: pd.DataFrame) -> pd.Series:
    return _rolling(data, _returns(data), TRADING_DAYS["3m"], "std")


def _volatility_6m(data: pd.DataFrame) -> pd.Series:
    return _rolling(data, _returns(data), TRADING_DAYS["6m"], "std")


def _reversal(data: pd.DataFrame) -> pd.Series:
    return -_ret_1m(data)


def _momentum_12_1(data: pd.DataFrame) -> pd.Series:
    close = data["close"]
    lag_1m = close.groupby(data["code"], sort=False).shift(TRADING_DAYS["1m"])
    lag_12m = close.groupby(data["code"], sort=False).shift(TRADING_DAYS["12m"])
    return safe_div(lag_1m, lag_12m) - 1.0


def _avg_amount_1m(data: pd.DataFrame) -> pd.Series:
    return _rolling(data, data["amount"], TRADING_DAYS["1m"], "mean")


def _log_amount_1m(data: pd.DataFrame) -> pd.Series:
    return np.log(_avg_amount_1m(data).where(lambda item: item > 0))


def _max_ret_1m(data: pd.DataFrame) -> pd.Series:
    return _rolling(data, _returns(data), TRADING_DAYS["1m"], "max")


def _min_ret_1m(data: pd.DataFrame) -> pd.Series:
    return _rolling(data, _returns(data), TRADING_DAYS["1m"], "min")


def _up_ratio_1m(data: pd.DataFrame) -> pd.Series:
    up = (_returns(data) > 0).astype(float)
    return _rolling(data, up, TRADING_DAYS["1m"], "mean")


def _ma_signal(data: pd.DataFrame) -> pd.Series:
    ma_20 = _rolling(data, data["close"], 20, "mean")
    return safe_div(data["close"], ma_20) - 1.0


def _vol_convergence(data: pd.DataFrame) -> pd.Series:
    return safe_div(_volatility_1m(data), _volatility_3m(data))


def _illiquidity(data: pd.DataFrame) -> pd.Series:
    daily = safe_div(_returns(data).abs(), data["amount"].replace(0, np.nan))
    return _rolling(data, daily, TRADING_DAYS["1m"], "mean")


def _log_price(data: pd.DataFrame) -> pd.Series:
    return np.log(data["close"].where(data["close"] > 0))


def _turnover_proxy(data: pd.DataFrame) -> pd.Series:
    base = _rolling(data, data["volume"], TRADING_DAYS["12m"], "mean")
    return safe_div(data["volume"], base)


def _volume_ratio(data: pd.DataFrame) -> pd.Series:
    short = _rolling(data, data["volume"], 5, "mean")
    long = _rolling(data, data["volume"], TRADING_DAYS["1m"], "mean")
    return safe_div(short, long)


def _high_low_1m(data: pd.DataFrame) -> pd.Series:
    high = _rolling(data, data["high"], TRADING_DAYS["1m"], "max")
    low = _rolling(data, data["low"], TRADING_DAYS["1m"], "min")
    return safe_div(high, low) - 1.0


def _rsi_14(data: pd.DataFrame) -> pd.Series:
    change = data.groupby("code")["close"].diff()
    gain = change.clip(lower=0)
    loss = (-change).clip(lower=0)
    avg_gain = _rolling(data, gain, 14, "mean")
    avg_loss = _rolling(data, loss, 14, "mean")
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    rsi = rsi.where(~((avg_loss == 0) & (avg_gain > 0)), 100.0)
    rsi = rsi.where(~((avg_loss == 0) & (avg_gain == 0)), 50.0)
    return rsi


def _bb_position(data: pd.DataFrame) -> pd.Series:
    mean = _rolling(data, data["close"], 20, "mean")
    std = _rolling(data, data["close"], 20, "std")
    lower = mean - 2.0 * std
    upper = mean + 2.0 * std
    return safe_div(data["close"] - lower, (upper - lower).replace(0, np.nan))


def _ret_3m_vol_adj(data: pd.DataFrame) -> pd.Series:
    return safe_div(_ret_3m(data), _volatility_3m(data))


def _amplitude_1m(data: pd.DataFrame) -> pd.Series:
    amplitude = safe_div(data["high"] - data["low"], data["close"].replace(0, np.nan))
    return _rolling(data, amplitude, TRADING_DAYS["1m"], "mean")


def _column_or_nan(data: pd.DataFrame, column: str) -> pd.Series:
    if column in data.columns:
        return data[column]
    return pd.Series(np.nan, index=data.index, dtype=float)


def _financial_ratio(data: pd.DataFrame, numerator: str, denominator: str) -> pd.Series:
    return safe_div(_column_or_nan(data, numerator), _column_or_nan(data, denominator).replace(0, np.nan))


def _roe_ttm(data: pd.DataFrame) -> pd.Series:
    return _financial_ratio(data, "net_profit_ttm", "equity")


def _roa_ttm(data: pd.DataFrame) -> pd.Series:
    return _financial_ratio(data, "net_profit_ttm", "assets")


def _net_margin(data: pd.DataFrame) -> pd.Series:
    return _financial_ratio(data, "net_profit_ttm", "revenue_ttm")


def _debt_to_asset(data: pd.DataFrame) -> pd.Series:
    return _financial_ratio(data, "liabilities", "assets")


def _revenue_yoy(data: pd.DataFrame) -> pd.Series:
    return _column_or_nan(data, "revenue_yoy")


def _profit_yoy(data: pd.DataFrame) -> pd.Series:
    return _column_or_nan(data, "profit_yoy")


def _eps_yoy(data: pd.DataFrame) -> pd.Series:
    return _column_or_nan(data, "eps_yoy")


def _asset_turnover(data: pd.DataFrame) -> pd.Series:
    return _financial_ratio(data, "revenue_ttm", "assets")


FINANCIAL_COLUMNS = (
    "net_profit_ttm",
    "equity",
    "assets",
    "revenue_ttm",
    "liabilities",
    "revenue_yoy",
    "profit_yoy",
    "eps_yoy",
)

FACTOR_FUNCTIONS = {
    "ret_1m": _ret_1m,
    "ret_3m": _ret_3m,
    "ret_6m": _ret_6m,
    "ret_12m": _ret_12m,
    "volatility_1m": _volatility_1m,
    "volatility_3m": _volatility_3m,
    "reversal": _reversal,
    "momentum_12_1": _momentum_12_1,
    "avg_amount_1m": _avg_amount_1m,
    "log_amount_1m": _log_amount_1m,
    "max_ret_1m": _max_ret_1m,
    "min_ret_1m": _min_ret_1m,
    "up_ratio_1m": _up_ratio_1m,
    "ma_signal": _ma_signal,
    "vol_convergence": _vol_convergence,
    "illiquidity": _illiquidity,
    "log_price": _log_price,
    "turnover_proxy": _turnover_proxy,
    "volatility_6m": _volatility_6m,
    "volume_ratio": _volume_ratio,
    "high_low_1m": _high_low_1m,
    "rsi_14": _rsi_14,
    "bb_position": _bb_position,
    "ret_3m_vol_adj": _ret_3m_vol_adj,
    "amplitude_1m": _amplitude_1m,
    "roe_ttm": _roe_ttm,
    "roa_ttm": _roa_ttm,
    "net_margin": _net_margin,
    "debt_to_asset": _debt_to_asset,
    "revenue_yoy": _revenue_yoy,
    "profit_yoy": _profit_yoy,
    "eps_yoy": _eps_yoy,
    "asset_turnover": _asset_turnover,
}
