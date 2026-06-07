# ============================================================
# WorldQuant Alpha101 Alpha#1-Alpha#10 因子实现
# 来源：WorldQuant "101 Formulaic Alphas" Appendix A
# 注意：与 GTJA191 GJ#1-GJ#10 编号体系完全不同
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
    ts_argmax,
    compute_vwap
)


# ============================================================
# Alpha#1-Alpha#10 实现
# ============================================================

def compute_alpha1(df):
    df = df.copy()
    prev_close = df.groupby('code')['close'].transform(lambda x: delay(x, 1))
    df['returns'] = df['close'] / prev_close - 1
    df['stddev_ret_20'] = df.groupby('code')['returns'].transform(lambda x: x.rolling(20).std())
    df['selected'] = np.where(df['returns'] < 0, df['stddev_ret_20'], df['close'])
    df['signed_power'] = df['selected'] ** 2
    df['ts_argmax'] = df.groupby('code')['signed_power'].transform(lambda x: ts_argmax(x, 5))
    df['alpha1'] = rank_cross_section(df, 'ts_argmax') - 0.5
    df['alpha1'] = df['alpha1'].replace([np.inf, -np.inf], np.nan)
    return df['alpha1']


def compute_alpha2(df):
    df = df.copy()
    df['log_vol'] = np.log(df['volume'].replace(0, np.nan))
    df['delta_log_vol'] = df.groupby('code')['log_vol'].transform(lambda x: delta(x, 2))
    df['rank_delta_log_vol'] = rank_cross_section(df, 'delta_log_vol')
    df['intraday_ret'] = (df['close'] - df['open']) / df['open'].replace(0, np.nan)
    df['rank_intraday_ret'] = rank_cross_section(df, 'intraday_ret')
    df['alpha2'] = df.groupby('code').apply(
        lambda g: ts_corr(g, 'rank_delta_log_vol', 'rank_intraday_ret', 6)
    ).reset_index(level=0, drop=True).reindex(df.index) * (-1)
    df['alpha2'] = df['alpha2'].replace([np.inf, -np.inf], np.nan)
    return df['alpha2']


def compute_alpha3(df):
    df = df.copy()
    df['rank_open'] = rank_cross_section(df, 'open')
    df['rank_volume'] = rank_cross_section(df, 'volume')
    df['alpha3'] = df.groupby('code').apply(
        lambda g: ts_corr(g, 'rank_open', 'rank_volume', 10)
    ).reset_index(level=0, drop=True).reindex(df.index) * (-1)
    df['alpha3'] = df['alpha3'].replace([np.inf, -np.inf], np.nan)
    return df['alpha3']


def compute_alpha4(df):
    df = df.copy()
    df['rank_low'] = rank_cross_section(df, 'low')
    df['alpha4'] = df.groupby('code')['rank_low'].transform(lambda x: tsrank(x, 9)) * (-1)
    df['alpha4'] = df['alpha4'].replace([np.inf, -np.inf], np.nan)
    return df['alpha4']


def compute_alpha5(df):
    df = df.copy()
    df['vwap'] = compute_vwap(df['close'], df['high'], df['low'], df['open'], df['amount'], df['volume'])
    df['vwap_ma10'] = df.groupby('code')['vwap'].transform(lambda x: x.rolling(10).mean())
    df['open_minus_vwapma'] = df['open'] - df['vwap_ma10']
    df['rank_open_vwap'] = rank_cross_section(df, 'open_minus_vwapma')
    df['close_minus_vwap'] = df['close'] - df['vwap']
    df['rank_close_vwap'] = rank_cross_section(df, 'close_minus_vwap')
    df['alpha5'] = df['rank_open_vwap'] * (-1 * np.abs(df['rank_close_vwap']))
    return df['alpha5']


def compute_alpha6(df):
    df = df.copy()
    df['alpha6'] = df.groupby('code').apply(
        lambda g: g['open'].rolling(10).corr(g['volume'])
    ).reset_index(level=0, drop=True).reindex(df.index) * (-1)
    df['alpha6'] = df['alpha6'].replace([np.inf, -np.inf], np.nan)
    return df['alpha6']


def compute_alpha7(df):
    df = df.copy()
    df['adv20'] = df.groupby('code')['amount'].transform(lambda x: x.rolling(20).mean())
    df['delta_close_7'] = df.groupby('code')['close'].transform(lambda x: delta(x, 7))
    df['abs_delta_close_7'] = np.abs(df['delta_close_7'])
    df['ts_rank_abs_dc7'] = df.groupby('code')['abs_delta_close_7'].transform(lambda x: tsrank(x, 60))
    df['sign_delta_close_7'] = np.sign(df['delta_close_7'])
    cond = df['volume'] > df['adv20']
    df['alpha7'] = np.where(
        cond, (-1 * df['ts_rank_abs_dc7']) * df['sign_delta_close_7'], -1.0
    )
    df['alpha7'] = df['alpha7'].replace([np.inf, -np.inf], np.nan)
    return df['alpha7']


def compute_alpha8(df):
    df = df.copy()
    prev_close = df.groupby('code')['close'].transform(lambda x: delay(x, 1))
    df['returns'] = df['close'] / prev_close - 1
    df['sum_open_5'] = df.groupby('code')['open'].transform(lambda x: x.rolling(5).sum())
    df['sum_ret_5'] = df.groupby('code')['returns'].transform(lambda x: x.rolling(5).sum())
    df['product'] = df['sum_open_5'] * df['sum_ret_5']
    df['delay_product_10'] = df.groupby('code')['product'].transform(lambda x: delay(x, 10))
    df['diff'] = df['product'] - df['delay_product_10']
    df['alpha8'] = rank_cross_section(df, 'diff') * (-1)
    return df['alpha8']


def compute_alpha9(df):
    df = df.copy()
    df['dc1'] = df.groupby('code')['close'].transform(lambda x: delta(x, 1))
    df['ts_min_dc1_5'] = df.groupby('code')['dc1'].transform(lambda x: tsmin(x, 5))
    df['ts_max_dc1_5'] = df.groupby('code')['dc1'].transform(lambda x: tsmax(x, 5))
    cond1 = df['ts_min_dc1_5'] > 0
    cond2 = df['ts_max_dc1_5'] < 0
    df['alpha9'] = np.where(
        cond1, df['dc1'], np.where(cond2, df['dc1'], -1 * df['dc1'])
    )
    df['alpha9'] = df['alpha9'].replace([np.inf, -np.inf], np.nan)
    return df['alpha9']


def compute_alpha10(df):
    df = df.copy()
    df['dc1'] = df.groupby('code')['close'].transform(lambda x: delta(x, 1))
    df['ts_min_dc1_4'] = df.groupby('code')['dc1'].transform(lambda x: tsmin(x, 4))
    df['ts_max_dc1_4'] = df.groupby('code')['dc1'].transform(lambda x: tsmax(x, 4))
    cond1 = df['ts_min_dc1_4'] > 0
    cond2 = df['ts_max_dc1_4'] < 0
    df['inner'] = np.where(
        cond1, df['dc1'], np.where(cond2, df['dc1'], -1 * df['dc1'])
    )
    df['alpha10'] = rank_cross_section(df, 'inner')
    df['alpha10'] = df['alpha10'].replace([np.inf, -np.inf], np.nan)
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
