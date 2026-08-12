"""
小市值策略 — 30~50亿区间，每月调仓

选股规则:
  1. 全A股中市值在 30亿 ~ 50亿 的股票
  2. 剔除ST/停牌
  3. 等权买入, 持有到下个月末
"""
import os
import pandas as pd
import numpy as np

STRATEGY_NAME = "小市值30-50亿"

_CACHE = None
_DATE_MAP = None


def _load_market_cap():
    global _CACHE, _DATE_MAP
    if _CACHE is not None:
        return _CACHE

    path = os.path.join(os.path.dirname(__file__), "..", "data", "market_cap_full.parquet")
    if not os.path.exists(path):
        print("  [30-50亿] ⚠️ 市值数据不存在")
        return None

    df = pd.read_parquet(path)
    df2 = df.reset_index()
    df2['symbol'] = df2['order_book_id'].str.replace('.XSHE', '.SZ').str.replace('.XSHG', '.SH')
    df2['mc_yi'] = df2['market_cap'] / 1e8
    date_map = {
        str(d): dict(zip(grp['symbol'], grp['mc_yi']))
        for d, grp in df2.groupby(df2['date'].dt.strftime('%Y-%m-%d'))
    }

    _DATE_MAP = date_map
    _CACHE = df
    print(f"  [30-50亿] 市值数据已加载: {len(df)}行, {len(date_map)}天")
    return df


def get_signals(data):
    """每月调仓: 选市值 30~50亿 的股票"""
    _load_market_cap()
    if _DATE_MAP is None:
        return pd.DataFrame(columns=['symbol', 'weight'])

    trade_date = str(data['trade_date'].iloc[0])[:10]
    symbols = data['symbol'].tolist()

    dates = sorted(_DATE_MAP.keys())
    if trade_date < dates[0]:
        return pd.DataFrame(columns=['symbol', 'weight'])
    valid_dates = [d for d in dates if d <= trade_date]
    latest_date = valid_dates[-1] if valid_dates else dates[-1]
    date_mc = _DATE_MAP[latest_date]

    mc_values = []
    valid_symbols = []
    for sym in symbols:
        mc = date_mc.get(sym)
        if mc is not None and mc > 0:
            mc_values.append(mc)
            valid_symbols.append(sym)

    if len(valid_symbols) < 100:
        return pd.DataFrame(columns=['symbol', 'weight'])

    # 30亿 <= 市值 < 50亿
    result = pd.DataFrame({'symbol': valid_symbols, 'market_cap': mc_values})
    filtered = result[(result['market_cap'] >= 30) & (result['market_cap'] < 50)].copy()

    if len(filtered) < 20:
        return pd.DataFrame(columns=['symbol', 'weight'])

    n = len(filtered)
    return pd.DataFrame({
        'symbol': filtered['symbol'].values,
        'weight': [1.0 / n] * n,
    })
