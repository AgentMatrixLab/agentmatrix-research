# ============================================================
# GTJA191 Alpha1-Alpha10 因子实现
# 来源：国泰君安《基于短周期价量特征的多因子选股体系》Table 6
# 注意：与 WorldQuant Alpha101 编号体系完全不同
# ============================================================

import numpy as np
import pandas as pd
from .operators import (
    rank_cross_section,
    tsrank,
    ts_corr,
    delta,
    delay,
    tsmax,
    tsmin,
    compute_vwap,
    sma_gtja
)


# ============================================================
# Alpha1-Alpha10 实现
# ============================================================

def compute_alpha1(df):
    df = df.copy()
    df['log_vol'] = np.log(df['volume'].replace(0, np.nan))
    df['delta_log_vol'] = df.groupby('code')['log_vol'].transform(lambda x: delta(x, 1))
    df['rank_delta_log_vol'] = rank_cross_section(df, 'delta_log_vol')
    df['intraday_ret'] = (df['close'] - df['open']) / df['open'].replace(0, np.nan)
    df['rank_intraday_ret'] = rank_cross_section(df, 'intraday_ret')
    df['alpha1'] = df.groupby('code').apply(
        lambda g: ts_corr(g, 'rank_delta_log_vol', 'rank_intraday_ret', 6)
    ).reset_index(level=0, drop=True).reindex(df.index) * (-1)
    df['alpha1'] = df['alpha1'].replace([np.inf, -np.inf], np.nan)
    return df['alpha1']


def compute_alpha2(df):
    df = df.copy()
    hl_range = df['high'] - df['low']
    hl_range = hl_range.replace(0, np.nan)
    df['power_diff'] = ((df['close'] - df['low']) - (df['high'] - df['close'])) / hl_range
    df['alpha2'] = df.groupby('code')['power_diff'].transform(lambda x: delta(x, 1)) * (-1)
    return df['alpha2']


def compute_alpha3(df):
    df = df.copy()
    prev_close = df.groupby('code')['close'].transform(lambda x: delay(x, 1))
    unchanged = df['close'] == prev_close
    rising = df['close'] > prev_close
    min_low_prev = np.minimum(df['low'], prev_close)
    falling = df['close'] < prev_close
    max_high_prev = np.maximum(df['high'], prev_close)
    df['eff_move'] = 0.0
    df.loc[rising, 'eff_move'] = df.loc[rising, 'close'] - min_low_prev[rising]
    df.loc[falling, 'eff_move'] = df.loc[falling, 'close'] - max_high_prev[falling]
    df['alpha3'] = df.groupby('code')['eff_move'].transform(lambda x: x.rolling(6).sum())
    return df['alpha3']


def compute_alpha4(df):
    df = df.copy()
    ma8 = df.groupby('code')['close'].transform(lambda x: x.rolling(8).mean())
    std8 = df.groupby('code')['close'].transform(lambda x: x.rolling(8).std())
    ma2 = df.groupby('code')['close'].transform(lambda x: x.rolling(2).mean())
    ma20_vol = df.groupby('code')['volume'].transform(lambda x: x.rolling(20).mean())
    vol_ratio = df['volume'] / ma20_vol.replace(0, np.nan)
    cond1 = (ma8 + std8) < ma2
    cond2 = ma2 < (ma8 - std8)
    cond3 = vol_ratio >= 1
    df['alpha4'] = np.where(cond1, -1.0, np.where(cond2, 1.0, np.where(cond3, 1.0, -1.0)))
    return df['alpha4']


def compute_alpha5(df):
    df = df.copy()
    df['tsrank_vol'] = df.groupby('code')['volume'].transform(lambda x: tsrank(x, 5))
    df['tsrank_high'] = df.groupby('code')['high'].transform(lambda x: tsrank(x, 5))
    df['corr_vh'] = df.groupby('code').apply(
        lambda g: ts_corr(g, 'tsrank_vol', 'tsrank_high', 5)
    ).reset_index(level=0, drop=True).reindex(df.index)
    df['corr_vh'] = df['corr_vh'].replace([np.inf, -np.inf], np.nan)
    df['alpha5'] = df.groupby('code')['corr_vh'].transform(lambda x: tsmax(x, 3)) * (-1)
    return df['alpha5']


def compute_alpha6(df):
    df = df.copy()
    df['weighted_price'] = df['open'] * 0.85 + df['high'] * 0.15
    df['delta_wp'] = df.groupby('code')['weighted_price'].transform(lambda x: delta(x, 4))
    df['sign_delta'] = np.sign(df['delta_wp'])
    df['alpha6'] = rank_cross_section(df, 'sign_delta') * (-1)
    return df['alpha6']


def compute_alpha7(df):
    df = df.copy()
    df['vwap'] = compute_vwap(df['close'], df['high'], df['low'], df['open'], df['amount'], df['volume'])
    df['vwap_close'] = df['vwap'] - df['close']
    df['tsmax_vc'] = df.groupby('code')['vwap_close'].transform(lambda x: tsmax(x, 3))
    df['tsmin_vc'] = df.groupby('code')['vwap_close'].transform(lambda x: tsmin(x, 3))
    df['delta_vol'] = df.groupby('code')['volume'].transform(lambda x: delta(x, 3))
    df['rank_tsmax'] = rank_cross_section(df, 'tsmax_vc')
    df['rank_tsmin'] = rank_cross_section(df, 'tsmin_vc')
    df['rank_delta_vol'] = rank_cross_section(df, 'delta_vol')
    df['alpha7'] = (df['rank_tsmax'] + df['rank_tsmin']) * df['rank_delta_vol']
    return df['alpha7']


def compute_alpha8(df):
    df = df.copy()
    df['vwap'] = compute_vwap(df['close'], df['high'], df['low'], df['open'], df['amount'], df['volume'])
    df['weighted_price'] = ((df['high'] + df['low']) / 2) * 0.2 + df['vwap'] * 0.8
    df['delta_wp'] = df.groupby('code')['weighted_price'].transform(lambda x: delta(x, 4))
    df['neg_delta'] = df['delta_wp'] * (-1)
    df['alpha8'] = rank_cross_section(df, 'neg_delta')
    return df['alpha8']


def compute_alpha9(df):
    df = df.copy()
    avg_price = (df['high'] + df['low']) / 2
    prev_avg_price = (df.groupby('code')['high'].transform(lambda x: delay(x, 1)) +
                      df.groupby('code')['low'].transform(lambda x: delay(x, 1))) / 2
    price_change = avg_price - prev_avg_price
    amplitude = df['high'] - df['low']
    volume_safe = df['volume'].replace(0, np.nan)
    raw_value = price_change * amplitude / volume_safe
    df['_raw9'] = raw_value
    df['alpha9'] = df.groupby('code')['_raw9'].transform(lambda x: sma_gtja(x, 7, 2))
    return df['alpha9']


def compute_alpha10(df):
    df = df.copy()
    prev_close = df.groupby('code')['close'].transform(lambda x: delay(x, 1))
    df['ret'] = df['close'] / prev_close - 1
    df['std_ret_20'] = df.groupby('code')['ret'].transform(lambda x: x.rolling(20).std())
    df['selected'] = np.where(df['ret'] < 0, df['std_ret_20'], df['close'])
    df['squared'] = df['selected'] ** 2
    df['tsmax_sq'] = df.groupby('code')['squared'].transform(lambda x: tsmax(x, 5))
    df['alpha10'] = rank_cross_section(df, 'tsmax_sq')
    return df['alpha10']


# ============================================================
# 统一计算入口
# ============================================================

def compute_all_alphas(df):
    df = df.sort_values(['date', 'code']).reset_index(drop=True)
    df['alpha1'] = compute_alpha1(df)
    df['alpha2'] = compute_alpha2(df)
    df['alpha3'] = compute_alpha3(df)
    df['alpha4'] = compute_alpha4(df)
    df['alpha5'] = compute_alpha5(df)
    df['alpha6'] = compute_alpha6(df)
    df['alpha7'] = compute_alpha7(df)
    df['alpha8'] = compute_alpha8(df)
    df['alpha9'] = compute_alpha9(df)
    df['alpha10'] = compute_alpha10(df)
    alpha_cols = [f'alpha{i}' for i in range(1, 11)]
    result = df[['date', 'code'] + alpha_cols].copy()
    return result
