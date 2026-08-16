from __future__ import annotations

import numpy as np
import pandas as pd

from research_core.factor_lab.operators import (
    compute_vwap,
    cross_sectional_rank,
    rolling_corr,
    safe_div,
    sort_panel,
    ts_delay,
    ts_delta,
    ts_max,
    ts_mean,
    ts_min,
    ts_rank,
)


IMPLEMENTED_GTJA191_FACTORS = tuple(f"alpha{i}" for i in range(1, 21))


def _sma_gtja(series: pd.Series, n: int, m: int) -> pd.Series:
    values = series.to_numpy(dtype=float)
    result = np.full(len(values), np.nan)
    start_idx = None
    for idx, value in enumerate(values):
        if not np.isnan(value):
            result[idx] = value
            start_idx = idx
            break
    if start_idx is None:
        return pd.Series(result, index=series.index)
    for idx in range(start_idx + 1, len(values)):
        result[idx] = result[idx - 1] if np.isnan(values[idx]) else (values[idx] * m + result[idx - 1] * (n - m)) / n
    return pd.Series(result, index=series.index)


def _cs_rank(df: pd.DataFrame, series: pd.Series, name: str) -> pd.Series:
    return cross_sectional_rank(df.assign(**{name: series}), name)


def _alpha1(df: pd.DataFrame) -> pd.Series:
    log_vol = np.log(df["volume"].replace(0, np.nan))
    delta_log_vol = ts_delta(df.assign(log_vol=log_vol), "log_vol", 1)
    rank_delta_log_vol = _cs_rank(df, delta_log_vol, "delta_log_vol")
    intraday_ret = safe_div(df["close"] - df["open"], df["open"].replace(0, np.nan))
    rank_intraday_ret = _cs_rank(df, intraday_ret, "intraday_ret")
    corr = rolling_corr(
        df.assign(rank_delta_log_vol=rank_delta_log_vol, rank_intraday_ret=rank_intraday_ret),
        "rank_delta_log_vol",
        "rank_intraday_ret",
        6,
    )
    return -corr


def _alpha2(df: pd.DataFrame) -> pd.Series:
    price_power = safe_div((df["close"] - df["low"]) - (df["high"] - df["close"]), (df["high"] - df["low"]).replace(0, np.nan))
    return -ts_delta(df.assign(price_power=price_power), "price_power", 1)


def _alpha3(df: pd.DataFrame) -> pd.Series:
    prev_close = ts_delay(df, "close", 1)
    rising = df["close"] > prev_close
    falling = df["close"] < prev_close
    eff_move = pd.Series(0.0, index=df.index)
    eff_move = eff_move.where(~rising, df["close"] - np.minimum(df["low"], prev_close))
    eff_move = eff_move.where(~falling, df["close"] - np.maximum(df["high"], prev_close))
    return df.assign(eff_move=eff_move).groupby("code")["eff_move"].transform(lambda x: x.rolling(6, min_periods=6).sum())


def _alpha4(df: pd.DataFrame) -> pd.Series:
    ma8 = ts_mean(df, "close", 8)
    std8 = df.groupby("code")["close"].transform(lambda x: x.rolling(8, min_periods=8).std())
    ma2 = ts_mean(df, "close", 2)
    ma20_vol = ts_mean(df, "volume", 20)
    vol_ratio = safe_div(df["volume"], ma20_vol.replace(0, np.nan))
    cond1 = (ma8 + std8) < ma2
    cond2 = ma2 < (ma8 - std8)
    cond3 = vol_ratio >= 1
    return pd.Series(np.where(cond1, -1.0, np.where(cond2, 1.0, np.where(cond3, 1.0, -1.0))), index=df.index)


def _alpha5(df: pd.DataFrame) -> pd.Series:
    tsrank_vol = ts_rank(df, "volume", 5)
    tsrank_high = ts_rank(df, "high", 5)
    corr = rolling_corr(df.assign(tsrank_vol=tsrank_vol, tsrank_high=tsrank_high), "tsrank_vol", "tsrank_high", 5)
    return -ts_max(df.assign(corr_vh=corr), "corr_vh", 3)


def _alpha6(df: pd.DataFrame) -> pd.Series:
    weighted_price = df["open"] * 0.85 + df["high"] * 0.15
    sign_delta = np.sign(ts_delta(df.assign(weighted_price=weighted_price), "weighted_price", 4))
    return -_cs_rank(df, sign_delta, "sign_delta")


def _alpha7(df: pd.DataFrame) -> pd.Series:
    vwap = compute_vwap(df)
    vwap_close = vwap - df["close"]
    tsmax_vc = ts_max(df.assign(vwap_close=vwap_close), "vwap_close", 3)
    tsmin_vc = ts_min(df.assign(vwap_close=vwap_close), "vwap_close", 3)
    delta_vol = ts_delta(df, "volume", 3)
    return (_cs_rank(df, tsmax_vc, "tsmax_vc") + _cs_rank(df, tsmin_vc, "tsmin_vc")) * _cs_rank(df, delta_vol, "delta_vol")


def _alpha8(df: pd.DataFrame) -> pd.Series:
    vwap = compute_vwap(df)
    weighted_price = ((df["high"] + df["low"]) / 2.0) * 0.2 + vwap * 0.8
    neg_delta = -ts_delta(df.assign(weighted_price=weighted_price), "weighted_price", 4)
    return _cs_rank(df, neg_delta, "neg_delta")


def _alpha9(df: pd.DataFrame) -> pd.Series:
    avg_price = (df["high"] + df["low"]) / 2.0
    prev_avg_price = (ts_delay(df, "high", 1) + ts_delay(df, "low", 1)) / 2.0
    raw_value = safe_div((avg_price - prev_avg_price) * (df["high"] - df["low"]), df["volume"].replace(0, np.nan))
    return df.assign(raw9=raw_value).groupby("code")["raw9"].transform(lambda x: _sma_gtja(x, 7, 2))


def _alpha10(df: pd.DataFrame) -> pd.Series:
    returns = df.groupby("code")["close"].pct_change()
    std_ret_20 = df.assign(returns=returns).groupby("code")["returns"].transform(lambda x: x.rolling(20, min_periods=20).std())
    selected = np.where(returns < 0, std_ret_20, df["close"])
    tsmax_sq = ts_max(df.assign(squared=pd.Series(selected, index=df.index) ** 2), "squared", 5)
    return _cs_rank(df, tsmax_sq, "tsmax_sq")


def _alpha11(df: pd.DataFrame) -> pd.Series:
    price_power = safe_div((df["close"] - df["low"]) - (df["high"] - df["close"]), (df["high"] - df["low"]).replace(0, np.nan))
    weighted_power = price_power * df["volume"]
    return df.assign(weighted_power=weighted_power).groupby("code")["weighted_power"].transform(lambda x: x.rolling(6, min_periods=6).sum())

def _alpha12(df: pd.DataFrame) -> pd.Series:
    vwap = compute_vwap(df)
    df_with_vwap = df.assign(vwap=vwap)

    vwap_mean_10 = ts_mean(df_with_vwap, "vwap", 10)

    left = _cs_rank(df, df["open"] - vwap_mean_10, "open_minus_vwap_mean_10")
    right = _cs_rank(df, (df["close"] - vwap).abs(), "abs_close_minus_vwap")

    return -left * right


def _alpha13(df: pd.DataFrame) -> pd.Series:
    vwap = compute_vwap(df)
    return np.sqrt(df["high"] * df["low"]) - vwap


def _alpha14(df: pd.DataFrame) -> pd.Series:
    return df["close"] - ts_delay(df, "close", 5)


def _alpha15(df: pd.DataFrame) -> pd.Series:
    prev_close = ts_delay(df, "close", 1)
    return safe_div(df["open"], prev_close.replace(0, np.nan)) - 1.0


def _alpha16(df: pd.DataFrame) -> pd.Series:
    vwap = compute_vwap(df)

    rank_volume = _cs_rank(df, df["volume"], "volume")
    rank_vwap = _cs_rank(df, vwap, "vwap")

    corr = rolling_corr(
        df.assign(rank_volume=rank_volume, rank_vwap=rank_vwap),
        "rank_volume",
        "rank_vwap",
        5,
    )

    rank_corr = _cs_rank(df, corr, "corr_rank_volume_vwap")

    return -ts_max(df.assign(rank_corr=rank_corr), "rank_corr", 5)


def _alpha17(df: pd.DataFrame) -> pd.Series:
    vwap = compute_vwap(df)
    df_with_vwap = df.assign(vwap=vwap)

    max_vwap_15 = ts_max(df_with_vwap, "vwap", 15)
    rank_vwap_gap = _cs_rank(
        df,
        vwap - max_vwap_15,
        "vwap_minus_max_vwap_15",
    )

    delta_close_5 = ts_delta(df, "close", 5)

    return pd.Series(
        np.power(rank_vwap_gap, delta_close_5),
        index=df.index,
    )


def _alpha18(df: pd.DataFrame) -> pd.Series:
    prev_close_5 = ts_delay(df, "close", 5)
    return safe_div(df["close"], prev_close_5.replace(0, np.nan))


def _alpha19(df: pd.DataFrame) -> pd.Series:
    prev_close_5 = ts_delay(df, "close", 5)
    close_diff = df["close"] - prev_close_5

    down_move = safe_div(close_diff, prev_close_5.replace(0, np.nan))
    up_move = safe_div(close_diff, df["close"].replace(0, np.nan))

    return pd.Series(
        np.where(
            df["close"] < prev_close_5,
            down_move,
            np.where(df["close"] == prev_close_5, 0.0, up_move),
        ),
        index=df.index,
    )


def _alpha20(df: pd.DataFrame) -> pd.Series:
    delayed_close = ts_delay(df, "close", 6)
    return safe_div(df["close"] - delayed_close, delayed_close) * 100


_FACTOR_FUNCTIONS = {
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
}


def compute_gtja191_alphas(df: pd.DataFrame, factor_names: list[str] | None = None) -> pd.DataFrame:
    data = sort_panel(df)
    requested = list(factor_names or IMPLEMENTED_GTJA191_FACTORS)
    invalid = [name for name in requested if name not in _FACTOR_FUNCTIONS]
    if invalid:
        raise ValueError(f"Unsupported GTJA191 factors: {invalid}")

    result = data[["date", "code"]].copy()
    for factor_name in requested:
        result[factor_name] = _FACTOR_FUNCTIONS[factor_name](data).replace([np.inf, -np.inf], np.nan)
    return result
