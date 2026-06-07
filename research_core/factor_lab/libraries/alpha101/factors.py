from __future__ import annotations

import numpy as np
import pandas as pd

from research_core.factor_lab.operators import (
    compute_vwap,
    cross_sectional_scale,
    cross_sectional_rank,
    indneutralize,
    rolling_corr,
    rolling_cov,
    safe_div,
    sort_panel,
    ts_argmax,
    ts_argmin,
    ts_decay_linear,
    ts_delay,
    ts_delta,
    ts_max,
    ts_mean,
    ts_min,
    ts_product,
    ts_rank,
    ts_std,
    ts_sum,
)


IMPLEMENTED_ALPHA101_FACTORS = (
    "alpha1",
    "alpha2",
    "alpha3",
    "alpha4",
    "alpha5",
    "alpha6",
    "alpha7",
    "alpha8",
    "alpha9",
    "alpha10",
    "alpha11",
    "alpha12",
    "alpha13",
    "alpha14",
    "alpha15",
    "alpha16",
    "alpha17",
    "alpha18",
    "alpha19",
    "alpha20",
    "alpha21",
    "alpha22",
    "alpha23",
    "alpha24",
    "alpha25",
    "alpha26",
    "alpha27",
    "alpha28",
    "alpha29",
    "alpha30",
    "alpha31",
    "alpha32",
    "alpha33",
    "alpha34",
    "alpha35",
    "alpha36",
    "alpha37",
    "alpha38",
    "alpha39",
    "alpha40",
    "alpha41",
    "alpha42",
    "alpha43",
    "alpha44",
    "alpha45",
    "alpha46",
    "alpha47",
    "alpha48",
    "alpha49",
    "alpha50",
    "alpha51",
    "alpha52",
    "alpha53",
    "alpha54",
    "alpha55",
    "alpha56",
    "alpha57",
    "alpha58",
    "alpha59",
    "alpha60",
    "alpha61",
    "alpha62",
    "alpha63",
    "alpha64",
    "alpha65",
    "alpha66",
    "alpha67",
    "alpha68",
    "alpha69",
    "alpha70",
    "alpha71",
    "alpha72",
    "alpha73",
    "alpha74",
    "alpha75",
    "alpha76",
    "alpha77",
    "alpha78",
    "alpha79",
    "alpha80",
    "alpha81",
    "alpha82",
    "alpha83",
    "alpha84",
    "alpha85",
    "alpha86",
    "alpha87",
    "alpha88",
    "alpha89",
    "alpha90",
    "alpha91",
    "alpha92",
    "alpha93",
    "alpha94",
    "alpha95",
    "alpha96",
    "alpha97",
    "alpha98",
    "alpha99",
    "alpha100",
    "alpha101",
)


def _returns(df: pd.DataFrame) -> pd.Series:
    return df.groupby("code")["close"].pct_change()


def _adv(df: pd.DataFrame, window: int) -> pd.Series:
    return ts_mean(df, "amount", window, min_periods=window)


def _w(value: float | int) -> int:
    return max(int(np.floor(value)), 1)


def _cs_rank(df: pd.DataFrame, series: pd.Series, name: str = "value") -> pd.Series:
    return cross_sectional_rank(df.assign(**{name: series}), name)


def _ts_rank_series(df: pd.DataFrame, series: pd.Series, window: float | int, name: str = "value") -> pd.Series:
    win = _w(window)
    return ts_rank(df.assign(**{name: series}), name, win, min_periods=win)


def _ts_sum_series(df: pd.DataFrame, series: pd.Series, window: float | int, name: str = "value") -> pd.Series:
    win = _w(window)
    return ts_sum(df.assign(**{name: series}), name, win, min_periods=win)


def _ts_product_series(df: pd.DataFrame, series: pd.Series, window: float | int, name: str = "value") -> pd.Series:
    win = _w(window)
    return ts_product(df.assign(**{name: series}), name, win, min_periods=win)


def _ts_mean_series(df: pd.DataFrame, series: pd.Series, window: float | int, name: str = "value") -> pd.Series:
    win = _w(window)
    return ts_mean(df.assign(**{name: series}), name, win, min_periods=win)


def _ts_min_series(df: pd.DataFrame, series: pd.Series, window: float | int, name: str = "value") -> pd.Series:
    win = _w(window)
    return ts_min(df.assign(**{name: series}), name, win, min_periods=win)


def _ts_max_series(df: pd.DataFrame, series: pd.Series, window: float | int, name: str = "value") -> pd.Series:
    win = _w(window)
    return ts_max(df.assign(**{name: series}), name, win, min_periods=win)


def _ts_argmax_series(df: pd.DataFrame, series: pd.Series, window: float | int, name: str = "value") -> pd.Series:
    win = _w(window)
    return ts_argmax(df.assign(**{name: series}), name, win, min_periods=win)


def _ts_argmin_series(df: pd.DataFrame, series: pd.Series, window: float | int, name: str = "value") -> pd.Series:
    win = _w(window)
    return ts_argmin(df.assign(**{name: series}), name, win, min_periods=win)


def _ts_decay_series(df: pd.DataFrame, series: pd.Series, window: float | int, name: str = "value") -> pd.Series:
    win = _w(window)
    return ts_decay_linear(df.assign(**{name: series}), name, win, min_periods=win)


def _ts_delta_series(df: pd.DataFrame, series: pd.Series, window: float | int, name: str = "value") -> pd.Series:
    win = _w(window)
    return ts_delta(df.assign(**{name: series}), name, win)


def _ts_delay_series(df: pd.DataFrame, series: pd.Series, window: float | int, name: str = "value") -> pd.Series:
    return ts_delay(df.assign(**{name: series}), name, _w(window))


def _rolling_corr_series(df: pd.DataFrame, left: pd.Series, right: pd.Series, window: float | int, *, left_name: str = "left", right_name: str = "right") -> pd.Series:
    win = _w(window)
    return rolling_corr(df.assign(**{left_name: left, right_name: right}), left_name, right_name, win, min_periods=win)


def _weighted(left: pd.Series, right: pd.Series, weight: float) -> pd.Series:
    return (left * weight) + (right * (1.0 - weight))


def _signed_power(base: pd.Series, exponent: pd.Series) -> pd.Series:
    return np.sign(base) * np.power(np.abs(base), exponent)


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


def _alpha11(df: pd.DataFrame) -> pd.Series:
    vwap = compute_vwap(df)
    vwap_close = vwap - df["close"]
    ts_max_vwap_close = ts_max(df.assign(vwap_close=vwap_close), "vwap_close", 3, min_periods=3)
    ts_min_vwap_close = ts_min(df.assign(vwap_close=vwap_close), "vwap_close", 3, min_periods=3)
    delta_volume = ts_delta(df, "volume", 3)
    rank_max = cross_sectional_rank(df.assign(ts_max_vwap_close=ts_max_vwap_close), "ts_max_vwap_close")
    rank_min = cross_sectional_rank(df.assign(ts_min_vwap_close=ts_min_vwap_close), "ts_min_vwap_close")
    rank_delta_volume = cross_sectional_rank(df.assign(delta_volume=delta_volume), "delta_volume")
    return (rank_max + rank_min) * rank_delta_volume


def _alpha12(df: pd.DataFrame) -> pd.Series:
    delta_volume = ts_delta(df, "volume", 1)
    delta_close = ts_delta(df, "close", 1)
    return pd.Series(np.sign(delta_volume) * (-delta_close), index=df.index, dtype=float)


def _alpha13(df: pd.DataFrame) -> pd.Series:
    rank_close = cross_sectional_rank(df, "close")
    rank_volume = cross_sectional_rank(df, "volume")
    cov = rolling_cov(
        df.assign(rank_close=rank_close, rank_volume=rank_volume),
        "rank_close",
        "rank_volume",
        5,
        min_periods=5,
    )
    return -cross_sectional_rank(df.assign(cov=cov), "cov")


def _alpha14(df: pd.DataFrame) -> pd.Series:
    returns = _returns(df)
    delta_returns = ts_delta(df.assign(returns=returns), "returns", 3)
    rank_delta_returns = cross_sectional_rank(df.assign(delta_returns=delta_returns), "delta_returns")
    corr = rolling_corr(df, "open", "volume", 10, min_periods=10)
    return -rank_delta_returns * corr


def _alpha15(df: pd.DataFrame) -> pd.Series:
    rank_high = cross_sectional_rank(df, "high")
    rank_volume = cross_sectional_rank(df, "volume")
    corr = rolling_corr(
        df.assign(rank_high=rank_high, rank_volume=rank_volume),
        "rank_high",
        "rank_volume",
        3,
        min_periods=3,
    )
    rank_corr = cross_sectional_rank(df.assign(corr=corr), "corr")
    sum_rank_corr = ts_sum(df.assign(rank_corr=rank_corr), "rank_corr", 3, min_periods=3)
    return -sum_rank_corr


def _alpha16(df: pd.DataFrame) -> pd.Series:
    rank_high = cross_sectional_rank(df, "high")
    rank_volume = cross_sectional_rank(df, "volume")
    cov = rolling_cov(
        df.assign(rank_high=rank_high, rank_volume=rank_volume),
        "rank_high",
        "rank_volume",
        5,
        min_periods=5,
    )
    return -cross_sectional_rank(df.assign(cov=cov), "cov")


def _alpha17(df: pd.DataFrame) -> pd.Series:
    adv20 = _adv(df, 20)
    ts_rank_close = ts_rank(df, "close", 10, min_periods=10)
    delta_close_1 = ts_delta(df, "close", 1)
    delta_delta_close = ts_delta(df.assign(delta_close_1=delta_close_1), "delta_close_1", 1)
    vol_adv = safe_div(df["amount"], adv20.replace(0, np.nan))
    ts_rank_vol_adv = ts_rank(df.assign(vol_adv=vol_adv), "vol_adv", 5, min_periods=5)
    rank_close_term = cross_sectional_rank(df.assign(ts_rank_close=ts_rank_close), "ts_rank_close")
    rank_delta_delta = cross_sectional_rank(df.assign(delta_delta_close=delta_delta_close), "delta_delta_close")
    rank_vol_term = cross_sectional_rank(df.assign(ts_rank_vol_adv=ts_rank_vol_adv), "ts_rank_vol_adv")
    return -rank_close_term * rank_delta_delta * rank_vol_term


def _alpha18(df: pd.DataFrame) -> pd.Series:
    close_open_diff = df["close"] - df["open"]
    std_abs = ts_std(df.assign(abs_diff=np.abs(close_open_diff)), "abs_diff", 5, min_periods=5)
    corr = rolling_corr(df, "close", "open", 10, min_periods=10)
    inner = std_abs + close_open_diff + corr
    return -cross_sectional_rank(df.assign(inner=inner), "inner")


def _alpha19(df: pd.DataFrame) -> pd.Series:
    delay_close_7 = ts_delay(df, "close", 7)
    delta_close_7 = ts_delta(df, "close", 7)
    returns = _returns(df)
    sum_returns_250 = ts_sum(df.assign(returns=returns), "returns", 250, min_periods=250)
    rank_sum_returns_250 = cross_sectional_rank(df.assign(sum_returns_250=sum_returns_250), "sum_returns_250")
    signal = (df["close"] - delay_close_7) + delta_close_7
    return (-np.sign(signal)) * (1.0 + rank_sum_returns_250)


def _alpha20(df: pd.DataFrame) -> pd.Series:
    delay_high = ts_delay(df, "high", 1)
    delay_close = ts_delay(df, "close", 1)
    delay_low = ts_delay(df, "low", 1)
    diff_high = df["open"] - delay_high
    diff_close = df["open"] - delay_close
    diff_low = df["open"] - delay_low
    rank_high = cross_sectional_rank(df.assign(diff_high=diff_high), "diff_high")
    rank_close = cross_sectional_rank(df.assign(diff_close=diff_close), "diff_close")
    rank_low = cross_sectional_rank(df.assign(diff_low=diff_low), "diff_low")
    return -rank_high * rank_close * rank_low


def _alpha21(df: pd.DataFrame) -> pd.Series:
    close_mean_8 = ts_mean(df, "close", 8, min_periods=8)
    close_std_8 = ts_std(df, "close", 8, min_periods=8)
    close_mean_2 = ts_mean(df, "close", 2, min_periods=2)
    adv20 = _adv(df, 20)
    amount_adv = safe_div(df["amount"], adv20.replace(0, np.nan))
    factor = np.where(
        (close_mean_8 + close_std_8) < close_mean_2,
        -1.0,
        np.where(close_mean_2 < (close_mean_8 - close_std_8), 1.0, np.where(amount_adv >= 1.0, 1.0, -1.0)),
    )
    return pd.Series(factor, index=df.index, dtype=float)


def _alpha22(df: pd.DataFrame) -> pd.Series:
    corr = rolling_corr(df, "high", "volume", 5, min_periods=5)
    delta_corr = ts_delta(df.assign(corr=corr), "corr", 5)
    std_close_20 = ts_std(df, "close", 20, min_periods=20)
    rank_std_close_20 = cross_sectional_rank(df.assign(std_close_20=std_close_20), "std_close_20")
    return -(delta_corr * rank_std_close_20)


def _alpha23(df: pd.DataFrame) -> pd.Series:
    mean_high_20 = ts_mean(df, "high", 20, min_periods=20)
    delta_high_2 = ts_delta(df, "high", 2)
    return pd.Series(np.where(mean_high_20 < df["high"], -delta_high_2, 0.0), index=df.index, dtype=float)


def _alpha24(df: pd.DataFrame) -> pd.Series:
    close_mean_100 = ts_mean(df, "close", 100, min_periods=100)
    delta_close_mean_100 = ts_delta(df.assign(close_mean_100=close_mean_100), "close_mean_100", 100)
    delay_close_100 = ts_delay(df, "close", 100)
    ratio = safe_div(delta_close_mean_100, delay_close_100.replace(0, np.nan))
    min_close_100 = ts_min(df, "close", 100, min_periods=100)
    delta_close_3 = ts_delta(df, "close", 3)
    factor = np.where((ratio < 0.05) | (ratio == 0.05), -(df["close"] - min_close_100), -delta_close_3)
    return pd.Series(factor, index=df.index, dtype=float)


def _alpha25(df: pd.DataFrame) -> pd.Series:
    returns = _returns(df)
    adv20 = _adv(df, 20)
    vwap = compute_vwap(df)
    inner = (((-returns) * adv20) * vwap) * (df["high"] - df["close"])
    return cross_sectional_rank(df.assign(inner=inner), "inner")


def _alpha26(df: pd.DataFrame) -> pd.Series:
    ts_rank_volume = ts_rank(df, "volume", 5, min_periods=5)
    ts_rank_high = ts_rank(df, "high", 5, min_periods=5)
    corr = rolling_corr(
        df.assign(ts_rank_volume=ts_rank_volume, ts_rank_high=ts_rank_high),
        "ts_rank_volume",
        "ts_rank_high",
        5,
        min_periods=5,
    )
    ts_max_corr = ts_max(df.assign(corr=corr), "corr", 3, min_periods=3)
    return -ts_max_corr


def _alpha27(df: pd.DataFrame) -> pd.Series:
    vwap = compute_vwap(df)
    rank_volume = cross_sectional_rank(df, "volume")
    rank_vwap = cross_sectional_rank(df.assign(vwap=vwap), "vwap")
    corr = rolling_corr(
        df.assign(rank_volume=rank_volume, rank_vwap=rank_vwap),
        "rank_volume",
        "rank_vwap",
        6,
        min_periods=6,
    )
    mean_corr_2 = ts_mean(df.assign(corr=corr), "corr", 2, min_periods=2)
    ranked = cross_sectional_rank(df.assign(mean_corr_2=mean_corr_2), "mean_corr_2")
    return pd.Series(np.where(ranked > 0.5, -1.0, 1.0), index=df.index, dtype=float)


def _alpha28(df: pd.DataFrame) -> pd.Series:
    adv20 = _adv(df, 20)
    corr_adv_low = rolling_corr(
        df.assign(adv20=adv20),
        "adv20",
        "low",
        5,
        min_periods=5,
    )
    inner = corr_adv_low + ((df["high"] + df["low"]) / 2.0) - df["close"]
    return cross_sectional_scale(df.assign(inner=inner), "inner")


def _alpha29(df: pd.DataFrame) -> pd.Series:
    delta_close_minus_one = _ts_delta_series(df, df["close"] - 1.0, 5, "close_minus_one")
    rank_delta = _cs_rank(df, -_cs_rank(df, delta_close_minus_one, "delta_close"), "rank_delta")
    ts_min_rank = _ts_min_series(df, rank_delta, 2, "rank_delta")
    log_sum = np.log(_ts_sum_series(df, ts_min_rank, 1, "ts_min_rank").replace(0, np.nan))
    scaled = cross_sectional_scale(df.assign(log_sum=log_sum), "log_sum")
    rank_scaled = _cs_rank(df, _cs_rank(df, scaled, "scaled_inner"), "rank_scaled")
    prod = _ts_product_series(df, rank_scaled, 5, "rank_scaled")
    left = _ts_min_series(df, prod, 5, "prod")
    returns = _returns(df)
    right = _ts_rank_series(df, _ts_delay_series(df, -returns, 6, "neg_returns"), 5, "delay_neg_returns")
    return left + right


def _alpha30(df: pd.DataFrame) -> pd.Series:
    sign_1 = np.sign(df["close"] - ts_delay(df, "close", 1))
    sign_2 = np.sign(ts_delay(df, "close", 1) - ts_delay(df, "close", 2))
    sign_3 = np.sign(ts_delay(df, "close", 2) - ts_delay(df, "close", 3))
    inner = sign_1 + sign_2 + sign_3
    rank_inner = cross_sectional_rank(df.assign(inner=inner), "inner")
    sum_volume_5 = ts_sum(df, "volume", 5, min_periods=5)
    sum_volume_20 = ts_sum(df, "volume", 20, min_periods=20)
    return safe_div((1.0 - rank_inner) * sum_volume_5, sum_volume_20.replace(0, np.nan))


def _alpha31(df: pd.DataFrame) -> pd.Series:
    adv20 = _adv(df, 20)
    delta_close_10 = ts_delta(df, "close", 10)
    rank_delta_close_10 = cross_sectional_rank(df.assign(delta_close_10=delta_close_10), "delta_close_10")
    nested_rank = cross_sectional_rank(df.assign(rank_delta_close_10=rank_delta_close_10), "rank_delta_close_10")
    decay = ts_decay_linear(df.assign(nested_rank=-nested_rank), "nested_rank", 10, min_periods=10)
    decay_rank = cross_sectional_rank(df.assign(decay=decay), "decay")
    triple_rank = cross_sectional_rank(df.assign(decay_rank=decay_rank), "decay_rank")
    delta_close_3 = ts_delta(df, "close", 3)
    rank_delta_close_3 = cross_sectional_rank(df.assign(delta_close_3=-delta_close_3), "delta_close_3")
    corr_adv_low = rolling_corr(df.assign(adv20=adv20), "adv20", "low", 12, min_periods=12)
    scaled_corr = cross_sectional_scale(df.assign(corr_adv_low=corr_adv_low), "corr_adv_low")
    return triple_rank + rank_delta_close_3 + np.sign(scaled_corr)


def _alpha32(df: pd.DataFrame) -> pd.Series:
    vwap = compute_vwap(df)
    close_mean_7 = ts_mean(df, "close", 7, min_periods=7)
    scaled_mean_gap = cross_sectional_scale(df.assign(mean_gap=close_mean_7 - df["close"]), "mean_gap")
    delay_close_5 = ts_delay(df, "close", 5)
    corr = rolling_corr(df.assign(vwap=vwap, delay_close_5=delay_close_5), "vwap", "delay_close_5", 230, min_periods=230)
    scaled_corr = cross_sectional_scale(df.assign(corr=corr), "corr")
    return scaled_mean_gap + (20.0 * scaled_corr)


def _alpha33(df: pd.DataFrame) -> pd.Series:
    inner = -1.0 * (1.0 - safe_div(df["open"], df["close"].replace(0, np.nan)))
    return cross_sectional_rank(df.assign(inner=inner), "inner")


def _alpha34(df: pd.DataFrame) -> pd.Series:
    returns = _returns(df)
    std_returns_2 = ts_std(df.assign(returns=returns), "returns", 2, min_periods=2)
    std_returns_5 = ts_std(df.assign(returns=returns), "returns", 5, min_periods=5)
    rank_std_ratio = cross_sectional_rank(
        df.assign(std_ratio=safe_div(std_returns_2, std_returns_5.replace(0, np.nan))),
        "std_ratio",
    )
    delta_close_1 = ts_delta(df, "close", 1)
    rank_delta_close_1 = cross_sectional_rank(df.assign(delta_close_1=delta_close_1), "delta_close_1")
    inner = (1.0 - rank_std_ratio) + (1.0 - rank_delta_close_1)
    return cross_sectional_rank(df.assign(inner=inner), "inner")


def _alpha35(df: pd.DataFrame) -> pd.Series:
    returns = _returns(df)
    ts_rank_volume_32 = ts_rank(df, "volume", 32, min_periods=32)
    ts_rank_chl_16 = ts_rank(df.assign(chl=(df["close"] + df["high"]) - df["low"]), "chl", 16, min_periods=16)
    ts_rank_returns_32 = ts_rank(df.assign(returns=returns), "returns", 32, min_periods=32)
    return ts_rank_volume_32 * (1.0 - ts_rank_chl_16) * (1.0 - ts_rank_returns_32)


def _alpha36(df: pd.DataFrame) -> pd.Series:
    returns = _returns(df)
    vwap = compute_vwap(df)
    adv20 = _adv(df, 20)
    corr_close_open_delay_volume = rolling_corr(
        df.assign(close_open=df["close"] - df["open"], delay_volume=ts_delay(df, "volume", 1)),
        "close_open",
        "delay_volume",
        15,
        min_periods=15,
    )
    rank_term_1 = cross_sectional_rank(df.assign(corr_term=corr_close_open_delay_volume), "corr_term")
    rank_term_2 = cross_sectional_rank(df.assign(open_close=df["open"] - df["close"]), "open_close")
    ts_rank_delay_returns = ts_rank(df.assign(delay_returns=-ts_delay(df.assign(returns=returns), "returns", 6)), "delay_returns", 5, min_periods=5)
    rank_term_3 = cross_sectional_rank(df.assign(ts_rank_delay_returns=ts_rank_delay_returns), "ts_rank_delay_returns")
    corr_vwap_adv20 = rolling_corr(df.assign(vwap=vwap, adv20=adv20), "vwap", "adv20", 6, min_periods=6)
    rank_term_4 = cross_sectional_rank(df.assign(abs_corr=np.abs(corr_vwap_adv20)), "abs_corr")
    mean_close_200 = ts_mean(df, "close", 200, min_periods=200)
    rank_term_5 = cross_sectional_rank(df.assign(inner=((mean_close_200 - df["open"]) * (df["close"] - df["open"]))), "inner")
    return (2.21 * rank_term_1) + (0.7 * rank_term_2) + (0.73 * rank_term_3) + rank_term_4 + (0.6 * rank_term_5)


def _alpha37(df: pd.DataFrame) -> pd.Series:
    open_close = df["open"] - df["close"]
    delay_open_close = ts_delay(df.assign(open_close=open_close), "open_close", 1)
    corr = rolling_corr(df.assign(delay_open_close=delay_open_close), "delay_open_close", "close", 200, min_periods=200)
    rank_corr = cross_sectional_rank(df.assign(corr=corr), "corr")
    rank_open_close = cross_sectional_rank(df.assign(open_close=open_close), "open_close")
    return rank_corr + rank_open_close


def _alpha38(df: pd.DataFrame) -> pd.Series:
    ts_rank_close_10 = ts_rank(df, "close", 10, min_periods=10)
    rank_ts_rank_close_10 = cross_sectional_rank(df.assign(ts_rank_close_10=ts_rank_close_10), "ts_rank_close_10")
    rank_close_open = cross_sectional_rank(df.assign(close_open=safe_div(df["close"], df["open"].replace(0, np.nan))), "close_open")
    return -rank_ts_rank_close_10 * rank_close_open


def _alpha39(df: pd.DataFrame) -> pd.Series:
    returns = _returns(df)
    adv20 = _adv(df, 20)
    delta_close_7 = ts_delta(df, "close", 7)
    decay_volume_adv = ts_decay_linear(df.assign(amount_adv=safe_div(df["amount"], adv20.replace(0, np.nan))), "amount_adv", 9, min_periods=9)
    rank_decay = cross_sectional_rank(df.assign(decay_volume_adv=decay_volume_adv), "decay_volume_adv")
    rank_delta_term = cross_sectional_rank(df.assign(delta_term=delta_close_7 * (1.0 - rank_decay)), "delta_term")
    sum_returns_250 = ts_sum(df.assign(returns=returns), "returns", 250, min_periods=250)
    rank_sum_returns_250 = cross_sectional_rank(df.assign(sum_returns_250=sum_returns_250), "sum_returns_250")
    return -rank_delta_term * (1.0 + rank_sum_returns_250)


def _alpha40(df: pd.DataFrame) -> pd.Series:
    std_high_10 = ts_std(df, "high", 10, min_periods=10)
    rank_std_high_10 = cross_sectional_rank(df.assign(std_high_10=std_high_10), "std_high_10")
    corr_high_volume_10 = rolling_corr(df, "high", "volume", 10, min_periods=10)
    return -rank_std_high_10 * corr_high_volume_10


def _alpha41(df: pd.DataFrame) -> pd.Series:
    vwap = compute_vwap(df)
    return np.sqrt(df["high"] * df["low"]) - vwap


def _alpha42(df: pd.DataFrame) -> pd.Series:
    vwap = compute_vwap(df)
    rank_vwap_close = cross_sectional_rank(df.assign(vwap_close=vwap - df["close"]), "vwap_close")
    rank_vwap_plus_close = cross_sectional_rank(df.assign(vwap_plus_close=vwap + df["close"]), "vwap_plus_close")
    return safe_div(rank_vwap_close, rank_vwap_plus_close.replace(0, np.nan))


def _alpha43(df: pd.DataFrame) -> pd.Series:
    adv20 = _adv(df, 20)
    amount_adv = safe_div(df["amount"], adv20.replace(0, np.nan))
    ts_rank_amount_adv = ts_rank(df.assign(amount_adv=amount_adv), "amount_adv", 20, min_periods=20)
    delta_close_7 = ts_delta(df, "close", 7)
    ts_rank_delta_close_7 = ts_rank(df.assign(delta_close_7=-delta_close_7), "delta_close_7", 8, min_periods=8)
    return ts_rank_amount_adv * ts_rank_delta_close_7


def _alpha44(df: pd.DataFrame) -> pd.Series:
    rank_volume = cross_sectional_rank(df, "volume")
    corr = rolling_corr(
        df.assign(rank_volume=rank_volume),
        "high",
        "rank_volume",
        5,
        min_periods=5,
    )
    return -corr


def _alpha45(df: pd.DataFrame) -> pd.Series:
    delay_close_5 = ts_delay(df, "close", 5)
    mean_delay_close_20 = ts_mean(df.assign(delay_close_5=delay_close_5), "delay_close_5", 20, min_periods=20)
    rank_mean_delay_close_20 = cross_sectional_rank(df.assign(mean_delay_close_20=mean_delay_close_20), "mean_delay_close_20")
    corr_close_volume_2 = rolling_corr(df, "close", "volume", 2, min_periods=2)
    sum_close_5 = ts_sum(df, "close", 5, min_periods=5)
    sum_close_20 = ts_sum(df, "close", 20, min_periods=20)
    corr_sum_close = rolling_corr(
        df.assign(sum_close_5=sum_close_5, sum_close_20=sum_close_20),
        "sum_close_5",
        "sum_close_20",
        2,
        min_periods=2,
    )
    rank_corr_sum_close = cross_sectional_rank(df.assign(corr_sum_close=corr_sum_close), "corr_sum_close")
    return -(rank_mean_delay_close_20 * corr_close_volume_2 * rank_corr_sum_close)


def _alpha46(df: pd.DataFrame) -> pd.Series:
    slope = ((ts_delay(df, "close", 20) - ts_delay(df, "close", 10)) / 10.0) - ((ts_delay(df, "close", 10) - df["close"]) / 10.0)
    factor = np.where(slope > 0.25, -1.0, np.where(slope < 0.0, 1.0, -(df["close"] - ts_delay(df, "close", 1))))
    return pd.Series(factor, index=df.index, dtype=float)


def _alpha47(df: pd.DataFrame) -> pd.Series:
    vwap = compute_vwap(df)
    adv20 = _adv(df, 20)
    inv_close = 1.0 / df["close"].replace(0, np.nan)
    rank_inv_close = cross_sectional_rank(df.assign(inv_close=inv_close), "inv_close")
    rank_high_close = cross_sectional_rank(df.assign(high_close=df["high"] - df["close"]), "high_close")
    high_mean_5 = ts_mean(df, "high", 5, min_periods=5)
    term_1 = safe_div(rank_inv_close * df["volume"], adv20.replace(0, np.nan))
    term_2 = safe_div(df["high"] * rank_high_close, high_mean_5.replace(0, np.nan))
    rank_vwap_delay = cross_sectional_rank(df.assign(vwap_delay=vwap - ts_delay(df.assign(vwap=vwap), "vwap", 5)), "vwap_delay")
    return (term_1 * term_2) - rank_vwap_delay


def _alpha48(df: pd.DataFrame) -> pd.Series:
    delta_close_1 = ts_delta(df, "close", 1)
    delay_close_1 = ts_delay(df, "close", 1)
    delta_delay_close_1 = ts_delta(df.assign(delay_close_1=delay_close_1), "delay_close_1", 1)
    corr = rolling_corr(
        df.assign(delta_close_1=delta_close_1, delta_delay_close_1=delta_delay_close_1),
        "delta_close_1",
        "delta_delay_close_1",
        250,
        min_periods=250,
    )
    numerator = safe_div(corr * delta_close_1, df["close"].replace(0, np.nan))
    neutralized = indneutralize(df.assign(numerator=numerator), "numerator", "subindustry")
    squared_return = np.square(safe_div(delta_close_1, delay_close_1.replace(0, np.nan)))
    denominator = ts_sum(df.assign(squared_return=squared_return), "squared_return", 250, min_periods=250)
    return safe_div(neutralized, denominator.replace(0, np.nan))


def _alpha49(df: pd.DataFrame) -> pd.Series:
    slope = ((ts_delay(df, "close", 20) - ts_delay(df, "close", 10)) / 10.0) - ((ts_delay(df, "close", 10) - df["close"]) / 10.0)
    factor = np.where(slope < -0.1, 1.0, -(df["close"] - ts_delay(df, "close", 1)))
    return pd.Series(factor, index=df.index, dtype=float)


def _alpha50(df: pd.DataFrame) -> pd.Series:
    vwap = compute_vwap(df)
    rank_volume = cross_sectional_rank(df, "volume")
    rank_vwap = cross_sectional_rank(df.assign(vwap=vwap), "vwap")
    corr = rolling_corr(
        df.assign(rank_volume=rank_volume, rank_vwap=rank_vwap),
        "rank_volume",
        "rank_vwap",
        5,
        min_periods=5,
    )
    rank_corr = cross_sectional_rank(df.assign(corr=corr), "corr")
    ts_max_rank_corr = ts_max(df.assign(rank_corr=rank_corr), "rank_corr", 5, min_periods=5)
    return -ts_max_rank_corr


def _alpha51(df: pd.DataFrame) -> pd.Series:
    slope = ((ts_delay(df, "close", 20) - ts_delay(df, "close", 10)) / 10.0) - ((ts_delay(df, "close", 10) - df["close"]) / 10.0)
    factor = np.where(slope < -0.05, 1.0, -(df["close"] - ts_delay(df, "close", 1)))
    return pd.Series(factor, index=df.index, dtype=float)


def _alpha52(df: pd.DataFrame) -> pd.Series:
    returns = _returns(df)
    ts_min_low_5 = ts_min(df, "low", 5, min_periods=5)
    delay_ts_min_low_5 = ts_delay(df.assign(ts_min_low_5=ts_min_low_5), "ts_min_low_5", 5)
    rank_returns = cross_sectional_rank(
        df.assign(momentum=safe_div(ts_sum(df.assign(returns=returns), "returns", 240, min_periods=240) - ts_sum(df.assign(returns=returns), "returns", 20, min_periods=20), 220.0)),
        "momentum",
    )
    ts_rank_volume_5 = ts_rank(df, "volume", 5, min_periods=5)
    return (((-ts_min_low_5) + delay_ts_min_low_5) * rank_returns) * ts_rank_volume_5


def _alpha53(df: pd.DataFrame) -> pd.Series:
    denominator = (df["close"] - df["low"]).replace(0, np.nan)
    inner = safe_div((df["close"] - df["low"]) - (df["high"] - df["close"]), denominator)
    delta_inner = ts_delta(df.assign(inner=inner), "inner", 9)
    return -delta_inner


def _alpha54(df: pd.DataFrame) -> pd.Series:
    numerator = -((df["low"] - df["close"]) * np.power(df["open"], 5))
    denominator = (df["low"] - df["high"]) * np.power(df["close"], 5)
    return safe_div(numerator, denominator.replace(0, np.nan))


def _alpha55(df: pd.DataFrame) -> pd.Series:
    min_low_12 = ts_min(df, "low", 12, min_periods=12)
    max_high_12 = ts_max(df, "high", 12, min_periods=12)
    normalized = safe_div(df["close"] - min_low_12, (max_high_12 - min_low_12).replace(0, np.nan))
    rank_close_low = cross_sectional_rank(df.assign(normalized=normalized), "normalized")
    rank_volume = cross_sectional_rank(df, "volume")
    corr = rolling_corr(
        df.assign(rank_close_low=rank_close_low, rank_volume=rank_volume),
        "rank_close_low",
        "rank_volume",
        6,
        min_periods=6,
    )
    return -corr


def _alpha56(df: pd.DataFrame) -> pd.Series:
    returns = _returns(df)
    sum_returns_10 = ts_sum(df.assign(returns=returns), "returns", 10, min_periods=10)
    sum_returns_2 = ts_sum(df.assign(returns=returns), "returns", 2, min_periods=2)
    sum_sum_returns_2_3 = ts_sum(df.assign(sum_returns_2=sum_returns_2), "sum_returns_2", 3, min_periods=3)
    rank_term_1 = cross_sectional_rank(df.assign(ratio=safe_div(sum_returns_10, sum_sum_returns_2_3.replace(0, np.nan))), "ratio")
    rank_term_2 = cross_sectional_rank(df.assign(returns_cap=returns * df["cap"]), "returns_cap")
    return -(rank_term_1 * rank_term_2)


def _alpha57(df: pd.DataFrame) -> pd.Series:
    vwap = compute_vwap(df)
    ts_argmax_close_30 = ts_argmax(df, "close", 30, min_periods=30)
    rank_ts_argmax = cross_sectional_rank(df.assign(ts_argmax_close_30=ts_argmax_close_30), "ts_argmax_close_30")
    decay_rank = ts_decay_linear(df.assign(rank_ts_argmax=rank_ts_argmax), "rank_ts_argmax", 2, min_periods=2)
    return -safe_div(df["close"] - vwap, decay_rank.replace(0, np.nan))


def _alpha58(df: pd.DataFrame) -> pd.Series:
    vwap = compute_vwap(df)
    neutral_vwap = indneutralize(df.assign(vwap=vwap), "vwap", "sector")
    corr = _rolling_corr_series(df, neutral_vwap, df["volume"], 3.92795, left_name="neutral_vwap", right_name="volume_raw")
    decay = _ts_decay_series(df, corr, 7.89291, "corr")
    return -_ts_rank_series(df, decay, 5.50322, "decay")


def _alpha59(df: pd.DataFrame) -> pd.Series:
    vwap = compute_vwap(df)
    mixed = _weighted(vwap, vwap, 0.728317)
    neutral = indneutralize(df.assign(mixed=mixed), "mixed", "industry")
    corr = _rolling_corr_series(df, neutral, df["volume"], 4.25197, left_name="neutral", right_name="volume_raw")
    decay = _ts_decay_series(df, corr, 16.2289, "corr")
    return -_ts_rank_series(df, decay, 8.19648, "decay")


def _alpha60(df: pd.DataFrame) -> pd.Series:
    price_position = safe_div(((df["close"] - df["low"]) - (df["high"] - df["close"])) * df["volume"], (df["high"] - df["low"]).replace(0, np.nan))
    rank_price_position = _cs_rank(df, price_position, "price_position")
    scale_term = cross_sectional_scale(df.assign(rank_price_position=rank_price_position), "rank_price_position")
    rank_argmax = _cs_rank(df, _ts_argmax_series(df, df["close"], 10, "close_raw"), "argmax")
    scale_argmax = cross_sectional_scale(df.assign(rank_argmax=rank_argmax), "rank_argmax")
    return -((2.0 * scale_term) - scale_argmax)


def _alpha61(df: pd.DataFrame) -> pd.Series:
    vwap = compute_vwap(df)
    rank_left = _cs_rank(df, vwap - _ts_min_series(df, vwap, 16.1219, "vwap_raw"), "left")
    adv180 = _adv(df, 180)
    corr = _rolling_corr_series(df, vwap, adv180, 17.9282, left_name="vwap_raw", right_name="adv180")
    rank_right = _cs_rank(df, corr, "right")
    return (rank_left < rank_right).astype(float)


def _alpha62(df: pd.DataFrame) -> pd.Series:
    vwap = compute_vwap(df)
    adv20 = _adv(df, 20)
    sum_adv20 = _ts_sum_series(df, adv20, 22.4101, "adv20")
    corr_left = _rolling_corr_series(df, vwap, sum_adv20, 9.91009, left_name="vwap_raw", right_name="sum_adv20")
    rank_left = _cs_rank(df, corr_left, "corr_left")
    cond = ((_cs_rank(df, df["open"], "open1") + _cs_rank(df, df["open"], "open2")) < (_cs_rank(df, (df["high"] + df["low"]) / 2.0, "mid") + _cs_rank(df, df["high"], "high_raw"))).astype(float)
    rank_right = _cs_rank(df, cond, "cond")
    return ((rank_left < rank_right).astype(float)) * -1.0


def _alpha63(df: pd.DataFrame) -> pd.Series:
    vwap = compute_vwap(df)
    neutral_close = indneutralize(df, "close", "industry")
    delta_neutral_close = _ts_delta_series(df, neutral_close, 2.25164, "neutral_close")
    left = _cs_rank(df, _ts_decay_series(df, delta_neutral_close, 8.22237, "delta_neutral_close"), "left")
    mix = _weighted(vwap, df["open"], 0.318108)
    adv180 = _adv(df, 180)
    sum_adv180 = _ts_sum_series(df, adv180, 37.2467, "adv180")
    corr = _rolling_corr_series(df, mix, sum_adv180, 13.557, left_name="mix", right_name="sum_adv180")
    right = _cs_rank(df, _ts_decay_series(df, corr, 12.2883, "corr"), "right")
    return (left - right) * -1.0


def _alpha64(df: pd.DataFrame) -> pd.Series:
    vwap = compute_vwap(df)
    weighted_open_low = _weighted(df["open"], df["low"], 0.178404)
    sum_weighted = _ts_sum_series(df, weighted_open_low, 12.7054, "weighted_open_low")
    adv120 = _adv(df, 120)
    sum_adv120 = _ts_sum_series(df, adv120, 12.7054, "adv120")
    left = _cs_rank(df, _rolling_corr_series(df, sum_weighted, sum_adv120, 16.6208, left_name="sum_weighted", right_name="sum_adv120"), "left")
    right_input = _weighted((df["high"] + df["low"]) / 2.0, vwap, 0.178404)
    right = _cs_rank(df, _ts_delta_series(df, right_input, 3.69741, "right_input"), "right")
    return ((left < right).astype(float)) * -1.0


def _alpha65(df: pd.DataFrame) -> pd.Series:
    vwap = compute_vwap(df)
    weighted_open_vwap = _weighted(df["open"], vwap, 0.00817205)
    adv60 = _adv(df, 60)
    sum_adv60 = _ts_sum_series(df, adv60, 8.6911, "adv60")
    left = _cs_rank(df, _rolling_corr_series(df, weighted_open_vwap, sum_adv60, 6.40374, left_name="weighted_open_vwap", right_name="sum_adv60"), "left")
    right = _cs_rank(df, df["open"] - _ts_min_series(df, df["open"], 13.635, "open_raw"), "right")
    return ((left < right).astype(float)) * -1.0


def _alpha66(df: pd.DataFrame) -> pd.Series:
    vwap = compute_vwap(df)
    left = _cs_rank(df, _ts_decay_series(df, _ts_delta_series(df, vwap, 3.51013, "vwap_raw"), 7.23052, "delta_vwap"), "left")
    ratio = safe_div(df["low"] - vwap, (df["open"] - ((df["high"] + df["low"]) / 2.0)).replace(0, np.nan))
    right = _ts_rank_series(df, _ts_decay_series(df, ratio, 11.4157, "ratio"), 6.72611, "right_decay")
    return (left + right) * -1.0


def _alpha67(df: pd.DataFrame) -> pd.Series:
    vwap = compute_vwap(df)
    left = _cs_rank(df, df["high"] - _ts_min_series(df, df["high"], 2.14593, "high_raw"), "left")
    neutral_vwap = indneutralize(df.assign(vwap=vwap), "vwap", "sector")
    neutral_adv20 = indneutralize(df.assign(adv20=_adv(df, 20)), "adv20", "subindustry")
    right = _cs_rank(df, _rolling_corr_series(df, neutral_vwap, neutral_adv20, 6.02936, left_name="neutral_vwap", right_name="neutral_adv20"), "right")
    return np.power(left, right) * -1.0


def _alpha68(df: pd.DataFrame) -> pd.Series:
    adv15 = _adv(df, 15)
    corr = _rolling_corr_series(df, _cs_rank(df, df["high"], "high_rank"), _cs_rank(df, adv15, "adv15_rank"), 8.91644, left_name="high_ranked", right_name="adv15_ranked")
    left = _ts_rank_series(df, corr, 13.9333, "corr")
    weighted_close_low = _weighted(df["close"], df["low"], 0.518371)
    right = _cs_rank(df, _ts_delta_series(df, weighted_close_low, 1.06157, "weighted_close_low"), "right")
    return ((left < right).astype(float)) * -1.0


def _alpha69(df: pd.DataFrame) -> pd.Series:
    vwap = compute_vwap(df)
    neutral_vwap = indneutralize(df.assign(vwap=vwap), "vwap", "industry")
    left = _cs_rank(df, _ts_max_series(df, _ts_delta_series(df, neutral_vwap, 2.72412, "neutral_vwap"), 4.79344, "delta_neutral_vwap"), "left")
    mixed = _weighted(df["close"], vwap, 0.490655)
    corr = _rolling_corr_series(df, mixed, _adv(df, 20), 4.92416, left_name="mixed", right_name="adv20")
    right = _ts_rank_series(df, corr, 9.0615, "corr")
    return np.power(left, right) * -1.0


def _alpha70(df: pd.DataFrame) -> pd.Series:
    left = _cs_rank(df, _ts_delta_series(df, compute_vwap(df), 1.29456, "vwap_raw"), "left")
    neutral_close = indneutralize(df, "close", "industry")
    corr = _rolling_corr_series(df, neutral_close, _adv(df, 50), 17.8256, left_name="neutral_close", right_name="adv50")
    right = _ts_rank_series(df, corr, 17.9171, "corr")
    return np.power(left, right) * -1.0


def _alpha71(df: pd.DataFrame) -> pd.Series:
    left_corr = _rolling_corr_series(df, _ts_rank_series(df, df["close"], 3.43976, "close_raw"), _ts_rank_series(df, _adv(df, 180), 12.0647, "adv180"), 18.0175, left_name="close_ts", right_name="adv180_ts")
    left = _ts_rank_series(df, _ts_decay_series(df, left_corr, 4.20501, "left_corr"), 15.6948, "left_decay")
    vwap = compute_vwap(df)
    rank_term = _cs_rank(df, (df["low"] + df["open"]) - (vwap + vwap), "rank_term")
    right = _ts_rank_series(df, _ts_decay_series(df, np.square(rank_term), 16.4662, "rank_sq"), 4.4388, "right_decay")
    return np.maximum(left, right)


def _alpha72(df: pd.DataFrame) -> pd.Series:
    vwap = compute_vwap(df)
    left = _cs_rank(df, _ts_decay_series(df, _rolling_corr_series(df, (df["high"] + df["low"]) / 2.0, _adv(df, 40), 8.93345, left_name="mid", right_name="adv40"), 10.1519, "left_corr"), "left")
    right_corr = _rolling_corr_series(df, _ts_rank_series(df, vwap, 3.72469, "vwap_raw"), _ts_rank_series(df, df["volume"], 18.5188, "volume_raw"), 6.86671, left_name="vwap_ts", right_name="volume_ts")
    right = _cs_rank(df, _ts_decay_series(df, right_corr, 2.95011, "right_corr"), "right")
    return safe_div(left, right.replace(0, np.nan))


def _alpha73(df: pd.DataFrame) -> pd.Series:
    vwap = compute_vwap(df)
    left = _cs_rank(df, _ts_decay_series(df, _ts_delta_series(df, vwap, 4.72775, "vwap_raw"), 2.91864, "delta_vwap"), "left")
    weighted_open_low = _weighted(df["open"], df["low"], 0.147155)
    inner = safe_div(_ts_delta_series(df, weighted_open_low, 2.03608, "weighted_open_low"), weighted_open_low.replace(0, np.nan)) * -1.0
    right = _ts_rank_series(df, _ts_decay_series(df, inner, 3.33829, "inner"), 16.7411, "right")
    return np.maximum(left, right) * -1.0


def _alpha74(df: pd.DataFrame) -> pd.Series:
    adv30 = _adv(df, 30)
    left = _cs_rank(df, _rolling_corr_series(df, df["close"], _ts_sum_series(df, adv30, 37.4843, "adv30"), 15.1365, left_name="close_raw", right_name="sum_adv30"), "left")
    vwap = compute_vwap(df)
    weighted_high_vwap = _weighted(df["high"], vwap, 0.0261661)
    right = _cs_rank(df, _rolling_corr_series(df, _cs_rank(df, weighted_high_vwap, "weighted_high_vwap"), _cs_rank(df, df["volume"], "volume_rank"), 11.4791, left_name="rank_weighted", right_name="rank_volume"), "right")
    return ((left < right).astype(float)) * -1.0


def _alpha75(df: pd.DataFrame) -> pd.Series:
    vwap = compute_vwap(df)
    left = _cs_rank(df, _rolling_corr_series(df, vwap, df["volume"], 4.24304, left_name="vwap_raw", right_name="volume_raw"), "left")
    right = _cs_rank(df, _rolling_corr_series(df, _cs_rank(df, df["low"], "low_rank"), _cs_rank(df, _adv(df, 50), "adv50_rank"), 12.4413, left_name="low_ranked", right_name="adv50_ranked"), "right")
    return (left < right).astype(float)


def _alpha76(df: pd.DataFrame) -> pd.Series:
    vwap = compute_vwap(df)
    left = _cs_rank(df, _ts_decay_series(df, _ts_delta_series(df, vwap, 1.24383, "vwap_raw"), 11.8259, "delta_vwap"), "left")
    neutral_low = indneutralize(df, "low", "sector")
    corr = _rolling_corr_series(df, neutral_low, _adv(df, 81), 8.14941, left_name="neutral_low", right_name="adv81")
    right = _ts_rank_series(df, _ts_decay_series(df, _ts_rank_series(df, corr, 19.569, "corr"), 17.1543, "corr_rank"), 19.383, "right")
    return np.maximum(left, right) * -1.0


def _alpha77(df: pd.DataFrame) -> pd.Series:
    vwap = compute_vwap(df)
    left_inner = (((df["high"] + df["low"]) / 2.0) + df["high"]) - (vwap + df["high"])
    left = _cs_rank(df, _ts_decay_series(df, left_inner, 20.0451, "left_inner"), "left")
    right = _cs_rank(df, _ts_decay_series(df, _rolling_corr_series(df, (df["high"] + df["low"]) / 2.0, _adv(df, 40), 3.1614, left_name="mid", right_name="adv40"), 5.64125, "right_corr"), "right")
    return np.minimum(left, right)


def _alpha78(df: pd.DataFrame) -> pd.Series:
    vwap = compute_vwap(df)
    weighted_low_vwap = _weighted(df["low"], vwap, 0.352233)
    left = _cs_rank(df, _rolling_corr_series(df, _ts_sum_series(df, weighted_low_vwap, 19.7428, "weighted_low_vwap"), _ts_sum_series(df, _adv(df, 40), 19.7428, "adv40"), 6.83313, left_name="sum_weighted", right_name="sum_adv40"), "left")
    right = _cs_rank(df, _rolling_corr_series(df, _cs_rank(df, vwap, "vwap_rank"), _cs_rank(df, df["volume"], "volume_rank"), 5.77492, left_name="rank_vwap", right_name="rank_volume"), "right")
    return np.power(left, right)


def _alpha79(df: pd.DataFrame) -> pd.Series:
    vwap = compute_vwap(df)
    weighted_close_open = _weighted(df["close"], df["open"], 0.60733)
    neutral = indneutralize(df.assign(weighted_close_open=weighted_close_open), "weighted_close_open", "sector")
    left = _cs_rank(df, _ts_delta_series(df, neutral, 1.23438, "neutral"), "left")
    right = _cs_rank(df, _rolling_corr_series(df, _ts_rank_series(df, vwap, 3.60973, "vwap_raw"), _ts_rank_series(df, _adv(df, 150), 9.18637, "adv150"), 14.6644, left_name="vwap_ts", right_name="adv150_ts"), "right")
    return (left < right).astype(float)


def _alpha80(df: pd.DataFrame) -> pd.Series:
    weighted_open_high = _weighted(df["open"], df["high"], 0.868128)
    neutral = indneutralize(df.assign(weighted_open_high=weighted_open_high), "weighted_open_high", "industry")
    left = _cs_rank(df, np.sign(_ts_delta_series(df, neutral, 4.04545, "neutral")), "left")
    right = _ts_rank_series(df, _rolling_corr_series(df, df["high"], _adv(df, 10), 5.11456, left_name="high_raw", right_name="adv10"), 5.53756, "right_corr")
    return np.power(left, right) * -1.0


def _alpha81(df: pd.DataFrame) -> pd.Series:
    vwap = compute_vwap(df)
    adv10 = _adv(df, 10)
    corr = _rolling_corr_series(df, vwap, _ts_sum_series(df, adv10, 49.6054, "adv10"), 8.47743, left_name="vwap_raw", right_name="sum_adv10")
    ranked = _cs_rank(df, np.power(_cs_rank(df, corr, "corr"), 4), "ranked_pow")
    prod = _ts_product_series(df, ranked, 14.9655, "ranked")
    left = _cs_rank(df, np.log(prod.replace(0, np.nan).abs()), "left")
    right = _cs_rank(df, _rolling_corr_series(df, _cs_rank(df, vwap, "vwap_rank"), _cs_rank(df, df["volume"], "volume_rank"), 5.07914, left_name="rank_vwap", right_name="rank_volume"), "right")
    return ((left < right).astype(float)) * -1.0


def _alpha82(df: pd.DataFrame) -> pd.Series:
    left = _cs_rank(df, _ts_decay_series(df, _ts_delta_series(df, df["open"], 1.46063, "open_raw"), 14.8717, "delta_open"), "left")
    neutral_volume = indneutralize(df, "volume", "sector")
    corr = _rolling_corr_series(df, neutral_volume, df["open"], 17.4842, left_name="neutral_volume", right_name="open_raw")
    right = _ts_rank_series(df, _ts_decay_series(df, corr, 6.92131, "corr"), 13.4283, "right")
    return np.minimum(left, right) * -1.0


def _alpha83(df: pd.DataFrame) -> pd.Series:
    vwap = compute_vwap(df)
    price_range_ratio = safe_div(df["high"] - df["low"], _ts_mean_series(df, df["close"], 5, "close_raw").replace(0, np.nan))
    left = _cs_rank(df, _ts_delay_series(df, price_range_ratio, 2, "price_range_ratio"), "left")
    right_rank = _cs_rank(df, _cs_rank(df, df["volume"], "volume_rank_inner"), "volume_rank_outer")
    denom = safe_div(price_range_ratio, (vwap - df["close"]).replace(0, np.nan))
    return safe_div(left * right_rank, denom.replace(0, np.nan))


def _alpha84(df: pd.DataFrame) -> pd.Series:
    vwap = compute_vwap(df)
    base = _ts_rank_series(df, vwap - _ts_max_series(df, vwap, 15.3217, "vwap_raw"), 20.7127, "base")
    exponent = _ts_delta_series(df, df["close"], 4.96796, "close_raw")
    return _signed_power(base, exponent)


def _alpha85(df: pd.DataFrame) -> pd.Series:
    left = _cs_rank(df, _rolling_corr_series(df, _weighted(df["high"], df["close"], 0.876703), _adv(df, 30), 9.61331, left_name="weighted_high_close", right_name="adv30"), "left")
    right = _cs_rank(df, _rolling_corr_series(df, _ts_rank_series(df, (df["high"] + df["low"]) / 2.0, 3.70596, "mid"), _ts_rank_series(df, df["volume"], 10.1595, "volume_raw"), 7.11408, left_name="mid_ts", right_name="volume_ts"), "right")
    return np.power(left, right)


def _alpha86(df: pd.DataFrame) -> pd.Series:
    vwap = compute_vwap(df)
    adv20 = _adv(df, 20)
    left = _ts_rank_series(df, _rolling_corr_series(df, df["close"], _ts_sum_series(df, adv20, 14.7444, "adv20"), 6.00049, left_name="close_raw", right_name="sum_adv20"), 20.4195, "left_corr")
    right = _cs_rank(df, (df["open"] + df["close"]) - (vwap + df["open"]), "right")
    return ((left < right).astype(float)) * -1.0


def _alpha87(df: pd.DataFrame) -> pd.Series:
    vwap = compute_vwap(df)
    left = _cs_rank(df, _ts_decay_series(df, _ts_delta_series(df, _weighted(df["close"], vwap, 0.369701), 1.91233, "weighted_close_vwap"), 2.65461, "left_delta"), "left")
    neutral_adv81 = indneutralize(df.assign(adv81=_adv(df, 81)), "adv81", "industry")
    right = _ts_rank_series(df, _ts_decay_series(df, np.abs(_rolling_corr_series(df, neutral_adv81, df["close"], 13.4132, left_name="neutral_adv81", right_name="close_raw")), 4.89768, "abs_corr"), 14.4535, "right")
    return np.maximum(left, right) * -1.0


def _alpha88(df: pd.DataFrame) -> pd.Series:
    left_inner = (_cs_rank(df, df["open"], "open_rank") + _cs_rank(df, df["low"], "low_rank")) - (_cs_rank(df, df["high"], "high_rank") + _cs_rank(df, df["close"], "close_rank"))
    left = _cs_rank(df, _ts_decay_series(df, left_inner, 8.06882, "left_inner"), "left")
    right_corr = _rolling_corr_series(df, _ts_rank_series(df, df["close"], 8.44728, "close_raw"), _ts_rank_series(df, _adv(df, 60), 20.6966, "adv60"), 8.01266, left_name="close_ts", right_name="adv60_ts")
    right = _ts_rank_series(df, _ts_decay_series(df, right_corr, 6.65053, "right_corr"), 2.61957, "right")
    return np.minimum(left, right)


def _alpha89(df: pd.DataFrame) -> pd.Series:
    left_corr = _rolling_corr_series(df, df["low"], _adv(df, 10), 6.94279, left_name="low_raw", right_name="adv10")
    left = _ts_rank_series(df, _ts_decay_series(df, left_corr, 5.51607, "left_corr"), 3.79744, "left")
    vwap = compute_vwap(df)
    neutral_vwap = indneutralize(df.assign(vwap=vwap), "vwap", "industry")
    right = _ts_rank_series(df, _ts_decay_series(df, _ts_delta_series(df, neutral_vwap, 3.48158, "neutral_vwap"), 10.1466, "delta_neutral_vwap"), 15.3012, "right")
    return left - right


def _alpha90(df: pd.DataFrame) -> pd.Series:
    left = _cs_rank(df, df["close"] - _ts_max_series(df, df["close"], 4.66719, "close_raw"), "left")
    neutral_adv40 = indneutralize(df.assign(adv40=_adv(df, 40)), "adv40", "subindustry")
    right = _ts_rank_series(df, _rolling_corr_series(df, neutral_adv40, df["low"], 5.38375, left_name="neutral_adv40", right_name="low_raw"), 3.21856, "right")
    return np.power(left, right) * -1.0


def _alpha91(df: pd.DataFrame) -> pd.Series:
    neutral_close = indneutralize(df, "close", "industry")
    corr = _rolling_corr_series(df, neutral_close, df["volume"], 9.74928, left_name="neutral_close", right_name="volume_raw")
    decay_1 = _ts_decay_series(df, corr, 16.398, "corr")
    left = _ts_rank_series(df, _ts_decay_series(df, decay_1, 3.83219, "decay_1"), 4.8667, "left")
    vwap = compute_vwap(df)
    right = _cs_rank(df, _ts_decay_series(df, _rolling_corr_series(df, vwap, _adv(df, 30), 4.01303, left_name="vwap_raw", right_name="adv30"), 2.6809, "right_corr"), "right")
    return (left - right) * -1.0


def _alpha92(df: pd.DataFrame) -> pd.Series:
    cond = ((((df["high"] + df["low"]) / 2.0) + df["close"]) < (df["low"] + df["open"])).astype(float)
    left = _ts_rank_series(df, _ts_decay_series(df, cond, 14.7221, "cond"), 18.8683, "left")
    right = _ts_rank_series(df, _ts_decay_series(df, _rolling_corr_series(df, _cs_rank(df, df["low"], "low_rank"), _cs_rank(df, _adv(df, 30), "adv30_rank"), 7.58555, left_name="rank_low", right_name="rank_adv30"), 6.94024, "right_corr"), 6.80584, "right")
    return np.minimum(left, right)


def _alpha93(df: pd.DataFrame) -> pd.Series:
    vwap = compute_vwap(df)
    neutral_vwap = indneutralize(df.assign(vwap=vwap), "vwap", "industry")
    left = _ts_rank_series(df, _ts_decay_series(df, _rolling_corr_series(df, neutral_vwap, _adv(df, 81), 17.4193, left_name="neutral_vwap", right_name="adv81"), 19.848, "left_corr"), 7.54455, "left")
    weighted_close_vwap = _weighted(df["close"], vwap, 0.524434)
    right = _cs_rank(df, _ts_decay_series(df, _ts_delta_series(df, weighted_close_vwap, 2.77377, "weighted_close_vwap"), 16.2664, "right_delta"), "right")
    return safe_div(left, right.replace(0, np.nan))


def _alpha94(df: pd.DataFrame) -> pd.Series:
    vwap = compute_vwap(df)
    left = _cs_rank(df, vwap - _ts_min_series(df, vwap, 11.5783, "vwap_raw"), "left")
    right = _ts_rank_series(df, _rolling_corr_series(df, _ts_rank_series(df, vwap, 19.6462, "vwap_raw"), _ts_rank_series(df, _adv(df, 60), 4.02992, "adv60"), 18.0926, left_name="vwap_ts", right_name="adv60_ts"), 2.70756, "right")
    return np.power(left, right) * -1.0


def _alpha95(df: pd.DataFrame) -> pd.Series:
    left = _cs_rank(df, df["open"] - _ts_min_series(df, df["open"], 12.4105, "open_raw"), "left")
    corr = _rolling_corr_series(df, _ts_sum_series(df, (df["high"] + df["low"]) / 2.0, 19.1351, "mid"), _ts_sum_series(df, _adv(df, 40), 19.1351, "adv40"), 12.8742, left_name="sum_mid", right_name="sum_adv40")
    right = _ts_rank_series(df, np.power(_cs_rank(df, corr, "corr"), 5), 11.7584, "right")
    return (left < right).astype(float)


def _alpha96(df: pd.DataFrame) -> pd.Series:
    vwap = compute_vwap(df)
    left_decay = _ts_decay_series(df, _rolling_corr_series(df, _cs_rank(df, vwap, "vwap_rank"), _cs_rank(df, df["volume"], "volume_rank"), 3.83878, left_name="rank_vwap", right_name="rank_volume"), 4.16783, "left_corr")
    left = _ts_rank_series(df, left_decay, 8.38151, "left")
    if int(left.notna().sum()) == 0:
        left = left_decay
    corr = _rolling_corr_series(df, _ts_rank_series(df, df["close"], 7.45404, "close_raw"), _ts_rank_series(df, _adv(df, 60), 4.13242, "adv60"), 3.65459, left_name="close_ts", right_name="adv60_ts")
    argmax = _ts_argmax_series(df, corr, 12.6556, "corr")
    right_decay = _ts_decay_series(df, argmax, 14.0365, "argmax")
    right = _ts_rank_series(df, right_decay, 13.4143, "right")
    if int(right.notna().sum()) == 0:
        right = right_decay
    return np.fmax(left, right) * -1.0


def _alpha97(df: pd.DataFrame) -> pd.Series:
    vwap = compute_vwap(df)
    weighted_low_vwap = _weighted(df["low"], vwap, 0.721001)
    neutral = indneutralize(df.assign(weighted_low_vwap=weighted_low_vwap), "weighted_low_vwap", "industry")
    left = _cs_rank(df, _ts_decay_series(df, _ts_delta_series(df, neutral, 3.3705, "neutral"), 20.4523, "delta_neutral"), "left")
    corr = _rolling_corr_series(df, _ts_rank_series(df, df["low"], 7.87871, "low_raw"), _ts_rank_series(df, _adv(df, 60), 17.255, "adv60"), 4.97547, left_name="low_ts", right_name="adv60_ts")
    right = _ts_rank_series(df, _ts_decay_series(df, _ts_rank_series(df, corr, 18.5925, "corr"), 15.7152, "corr_rank"), 6.71659, "right")
    return (left - right) * -1.0


def _alpha98(df: pd.DataFrame) -> pd.Series:
    vwap = compute_vwap(df)
    left = _cs_rank(df, _ts_decay_series(df, _rolling_corr_series(df, vwap, _ts_sum_series(df, _adv(df, 5), 26.4719, "adv5"), 4.58418, left_name="vwap_raw", right_name="sum_adv5"), 7.18088, "left_corr"), "left")
    corr = _rolling_corr_series(df, _cs_rank(df, df["open"], "open_rank"), _cs_rank(df, _adv(df, 15), "adv15_rank"), 20.8187, left_name="open_ranked", right_name="adv15_ranked")
    argmin = _ts_argmin_series(df, corr, 8.62571, "corr")
    right = _cs_rank(df, _ts_decay_series(df, _ts_rank_series(df, argmin, 6.95668, "argmin"), 8.07206, "right_rank"), "right")
    return left - right


def _alpha99(df: pd.DataFrame) -> pd.Series:
    left = _cs_rank(df, _rolling_corr_series(df, _ts_sum_series(df, (df["high"] + df["low"]) / 2.0, 19.8975, "mid"), _ts_sum_series(df, _adv(df, 60), 19.8975, "adv60"), 8.8136, left_name="sum_mid", right_name="sum_adv60"), "left")
    right = _cs_rank(df, _rolling_corr_series(df, df["low"], df["volume"], 6.28259, left_name="low_raw", right_name="volume_raw"), "right")
    return ((left < right).astype(float)) * -1.0


def _alpha100(df: pd.DataFrame) -> pd.Series:
    price_position = safe_div(((df["close"] - df["low"]) - (df["high"] - df["close"])) * df["volume"], (df["high"] - df["low"]).replace(0, np.nan))
    rank_position = _cs_rank(df, price_position, "price_position")
    neutral_rank = indneutralize(df.assign(rank_position=rank_position), "rank_position", "subindustry")
    neutral_rank = indneutralize(df.assign(neutral_rank=neutral_rank), "neutral_rank", "subindustry")
    left = cross_sectional_scale(df.assign(neutral_rank=neutral_rank), "neutral_rank") * 1.5
    adv20 = _adv(df, 20)
    corr = _rolling_corr_series(df, df["close"], _cs_rank(df, adv20, "adv20_rank"), 5, left_name="close_raw", right_name="adv20_ranked")
    rank_argmin = _cs_rank(df, _ts_argmin_series(df, df["close"], 30, "close_raw"), "argmin")
    neutral_right = indneutralize(df.assign(right_term=corr - rank_argmin), "right_term", "subindustry")
    right = cross_sectional_scale(df.assign(neutral_right=neutral_right), "neutral_right")
    return -((left - right) * safe_div(df["volume"], adv20.replace(0, np.nan)))


def _alpha101(df: pd.DataFrame) -> pd.Series:
    return safe_div(df["close"] - df["open"], (df["high"] - df["low"] + 0.001))


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
    "alpha11": _alpha11,
    "alpha12": _alpha12,
    "alpha13": _alpha13,
    "alpha14": _alpha14,
    "alpha15": _alpha15,
    "alpha16": _alpha16,
    "alpha17": _alpha17,
    "alpha18": _alpha18,
    "alpha19": _alpha19,
    "alpha20": _alpha20,
    "alpha21": _alpha21,
    "alpha22": _alpha22,
    "alpha23": _alpha23,
    "alpha24": _alpha24,
    "alpha25": _alpha25,
    "alpha26": _alpha26,
    "alpha27": _alpha27,
    "alpha28": _alpha28,
    "alpha29": _alpha29,
    "alpha30": _alpha30,
    "alpha31": _alpha31,
    "alpha32": _alpha32,
    "alpha33": _alpha33,
    "alpha34": _alpha34,
    "alpha35": _alpha35,
    "alpha36": _alpha36,
    "alpha37": _alpha37,
    "alpha38": _alpha38,
    "alpha39": _alpha39,
    "alpha40": _alpha40,
    "alpha41": _alpha41,
    "alpha42": _alpha42,
    "alpha43": _alpha43,
    "alpha44": _alpha44,
    "alpha45": _alpha45,
    "alpha46": _alpha46,
    "alpha47": _alpha47,
    "alpha48": _alpha48,
    "alpha49": _alpha49,
    "alpha50": _alpha50,
    "alpha51": _alpha51,
    "alpha52": _alpha52,
    "alpha53": _alpha53,
    "alpha54": _alpha54,
    "alpha55": _alpha55,
    "alpha56": _alpha56,
    "alpha57": _alpha57,
    "alpha58": _alpha58,
    "alpha59": _alpha59,
    "alpha60": _alpha60,
    "alpha61": _alpha61,
    "alpha62": _alpha62,
    "alpha63": _alpha63,
    "alpha64": _alpha64,
    "alpha65": _alpha65,
    "alpha66": _alpha66,
    "alpha67": _alpha67,
    "alpha68": _alpha68,
    "alpha69": _alpha69,
    "alpha70": _alpha70,
    "alpha71": _alpha71,
    "alpha72": _alpha72,
    "alpha73": _alpha73,
    "alpha74": _alpha74,
    "alpha75": _alpha75,
    "alpha76": _alpha76,
    "alpha77": _alpha77,
    "alpha78": _alpha78,
    "alpha79": _alpha79,
    "alpha80": _alpha80,
    "alpha81": _alpha81,
    "alpha82": _alpha82,
    "alpha83": _alpha83,
    "alpha84": _alpha84,
    "alpha85": _alpha85,
    "alpha86": _alpha86,
    "alpha87": _alpha87,
    "alpha88": _alpha88,
    "alpha89": _alpha89,
    "alpha90": _alpha90,
    "alpha91": _alpha91,
    "alpha92": _alpha92,
    "alpha93": _alpha93,
    "alpha94": _alpha94,
    "alpha95": _alpha95,
    "alpha96": _alpha96,
    "alpha97": _alpha97,
    "alpha98": _alpha98,
    "alpha99": _alpha99,
    "alpha100": _alpha100,
    "alpha101": _alpha101,
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
    requested_set = set(requested)
    extra_requirements = {
        "sector": {"alpha58", "alpha67", "alpha76", "alpha79", "alpha82"},
        "industry": {"alpha59", "alpha63", "alpha69", "alpha70", "alpha80", "alpha87", "alpha89", "alpha91", "alpha93", "alpha97"},
        "subindustry": {"alpha48", "alpha67", "alpha90", "alpha100"},
        "cap": {"alpha56"},
    }
    extra_missing = sorted(
        column for column, factors in extra_requirements.items() if requested_set & factors and column not in data.columns
    )
    if extra_missing:
        raise ValueError(f"Missing required columns for Alpha101 computation: {extra_missing}")

    factor_payload: dict[str, pd.Series] = {}
    for factor_name in requested:
        factor = FACTOR_FUNCTIONS[factor_name](data)
        factor_payload[factor_name] = pd.Series(factor, index=data.index).replace([np.inf, -np.inf], np.nan)
    return pd.concat([data[["date", "code"]].copy(), pd.DataFrame(factor_payload, index=data.index)], axis=1)
