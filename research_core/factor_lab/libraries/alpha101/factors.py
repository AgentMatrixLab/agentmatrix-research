from __future__ import annotations

import numpy as np
import pandas as pd

from research_core.factor_lab.operators import (
    compute_vwap,
    cross_sectional_rank,
    rolling_corr,
    safe_div,
    sort_panel,
    ts_argmax,
    ts_delay,
    ts_delta,
    ts_max,
    ts_mean,
    ts_min,
    ts_rank,
    ts_std,
    ts_sum,
)


IMPLEMENTED_ALPHA101_FACTORS = tuple(f"alpha{i}" for i in range(1, 11))


def _alpha1(df: pd.DataFrame) -> pd.Series:
    returns = df.groupby("code")["close"].pct_change()
    std_20 = ts_std(df.assign(returns=returns), "returns", 20, min_periods=20)
    selected = np.where(returns < 0, std_20, df["close"])
    signed_power = np.sign(selected) * np.square(selected)
    argmax_5 = ts_argmax(df.assign(signed_power=signed_power), "signed_power", 5, min_periods=5)
    ranked = cross_sectional_rank(df.assign(argmax_5=argmax_5), "argmax_5")
    return ranked - 0.5


def _alpha2(df: pd.DataFrame) -> pd.Series:
    log_volume = np.log(df["volume"].replace(0, np.nan))
    delta_log_volume = ts_delta(df.assign(log_volume=log_volume), "log_volume", 2)
    intraday_return = safe_div(df["close"] - df["open"], df["open"].replace(0, np.nan))
    rank_delta = cross_sectional_rank(df.assign(delta_log_volume=delta_log_volume), "delta_log_volume")
    rank_intraday = cross_sectional_rank(df.assign(intraday_return=intraday_return), "intraday_return")
    corr = rolling_corr(
        df.assign(rank_delta=rank_delta, rank_intraday=rank_intraday),
        "rank_delta",
        "rank_intraday",
        6,
        min_periods=6,
    )
    return -corr


def _alpha3(df: pd.DataFrame) -> pd.Series:
    rank_open = cross_sectional_rank(df, "open")
    rank_volume = cross_sectional_rank(df, "volume")
    corr = rolling_corr(
        df.assign(rank_open=rank_open, rank_volume=rank_volume),
        "rank_open",
        "rank_volume",
        10,
        min_periods=10,
    )
    return -corr


def _alpha4(df: pd.DataFrame) -> pd.Series:
    rank_low = cross_sectional_rank(df, "low")
    ts_rank_low = ts_rank(df.assign(rank_low=rank_low), "rank_low", 9, min_periods=9)
    return -ts_rank_low


def _alpha5(df: pd.DataFrame) -> pd.Series:
    vwap = compute_vwap(df)
    vwap_ma10 = ts_mean(df.assign(vwap=vwap), "vwap", 10, min_periods=10)
    open_minus_vwapma = df["open"] - vwap_ma10
    close_minus_vwap = df["close"] - vwap
    rank_open_vwap = cross_sectional_rank(df.assign(open_minus_vwapma=open_minus_vwapma), "open_minus_vwapma")
    rank_close_vwap = cross_sectional_rank(df.assign(close_minus_vwap=close_minus_vwap), "close_minus_vwap")
    return rank_open_vwap * (-np.abs(rank_close_vwap))


def _alpha6(df: pd.DataFrame) -> pd.Series:
    corr = rolling_corr(df, "open", "volume", 10, min_periods=10)
    return -corr


def _alpha7(df: pd.DataFrame) -> pd.Series:
    adv20 = ts_mean(df, "amount", 20, min_periods=20)
    delta_close_7 = ts_delta(df, "close", 7)
    abs_delta_close_7 = np.abs(delta_close_7)
    ts_rank_abs = ts_rank(df.assign(abs_delta_close_7=abs_delta_close_7), "abs_delta_close_7", 60, min_periods=60)
    sign_delta_close_7 = np.sign(delta_close_7)
    factor = (-ts_rank_abs) * sign_delta_close_7
    return pd.Series(np.where(df["volume"] > adv20, factor, -1.0), index=df.index, dtype=float)


def _alpha8(df: pd.DataFrame) -> pd.Series:
    returns = df.groupby("code")["close"].pct_change()
    sum_open_5 = ts_sum(df, "open", 5, min_periods=5)
    sum_ret_5 = ts_sum(df.assign(returns=returns), "returns", 5, min_periods=5)
    product = sum_open_5 * sum_ret_5
    delay_product_10 = ts_delay(df.assign(product=product), "product", 10)
    diff = product - delay_product_10
    return -cross_sectional_rank(df.assign(diff=diff), "diff")


def _alpha9(df: pd.DataFrame) -> pd.Series:
    delta_close_1 = ts_delta(df, "close", 1)
    ts_min_dc1 = ts_min(df.assign(delta_close_1=delta_close_1), "delta_close_1", 5, min_periods=5)
    ts_max_dc1 = ts_max(df.assign(delta_close_1=delta_close_1), "delta_close_1", 5, min_periods=5)
    factor = np.where(ts_min_dc1 > 0, delta_close_1, np.where(ts_max_dc1 < 0, delta_close_1, -delta_close_1))
    return pd.Series(factor, index=df.index, dtype=float)


def _alpha10(df: pd.DataFrame) -> pd.Series:
    delta_close_1 = ts_delta(df, "close", 1)
    ts_min_dc1 = ts_min(df.assign(delta_close_1=delta_close_1), "delta_close_1", 4, min_periods=4)
    ts_max_dc1 = ts_max(df.assign(delta_close_1=delta_close_1), "delta_close_1", 4, min_periods=4)
    inner = np.where(ts_min_dc1 > 0, delta_close_1, np.where(ts_max_dc1 < 0, delta_close_1, -delta_close_1))
    return cross_sectional_rank(df.assign(inner=inner), "inner")


FACTOR_FUNCTIONS = {
    "alpha1": _alpha1,
    "alpha2": _alpha2,
    "alpha3": _alpha3,
    "alpha4": _alpha4,
    "alpha5": _alpha5,
    "alpha6": _alpha6,
    "alpha7": _alpha7,
    "alpha8": _alpha8,
    "alpha9": _alpha9,
    "alpha10": _alpha10,
}


def compute_alpha101_factors(
    df: pd.DataFrame,
    *,
    factor_names: list[str] | None = None,
) -> pd.DataFrame:
    data = sort_panel(df)
    required_columns = {"date", "code", "open", "high", "low", "close", "volume", "amount"}
    missing = sorted(required_columns - set(data.columns))
    if missing:
        raise ValueError(f"Missing required columns for Alpha101 computation: {missing}")

    requested = factor_names or list(IMPLEMENTED_ALPHA101_FACTORS)
    invalid = [name for name in requested if name not in FACTOR_FUNCTIONS]
    if invalid:
        raise ValueError(f"Unsupported Alpha101 factors: {invalid}")

    result = data[["date", "code"]].copy()
    for factor_name in requested:
        factor = FACTOR_FUNCTIONS[factor_name](data)
        result[factor_name] = pd.Series(factor, index=data.index).replace([np.inf, -np.inf], np.nan)
    return result
