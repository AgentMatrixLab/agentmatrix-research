"""
小市值策略 — 最小100只，每月调仓

选股规则:
  1. 全A股中选市值最小的100只股票
  2. 剔除ST/停牌
  3. 等权买入, 持有到下个月末
"""
import os
import pandas as pd
import numpy as np

STRATEGY_NAME = "小市值Top100"

# 复用同一个小市值数据缓存
_SM_CACHE = None
_SM_DATE_MAP = None


def _load_market_cap():
    """加载市值数据并建立快速查找索引"""
    global _SM_CACHE, _SM_DATE_MAP
    if _SM_CACHE is not None:
        return _SM_CACHE

    path = os.path.join(os.path.dirname(__file__), "..", "data", "market_cap_full.parquet")
    if not os.path.exists(path):
        print("  [小市值Top100] ⚠️ 市值数据不存在")
        return None

    df = pd.read_parquet(path)
    df2 = df.reset_index()
    df2['symbol'] = df2['order_book_id'].str.replace('.XSHE', '.SZ').str.replace('.XSHG', '.SH')
    df2['mc_yi'] = df2['market_cap'] / 1e8
    date_map = {
        str(d): dict(zip(grp['symbol'], grp['mc_yi']))
        for d, grp in df2.groupby(df2['date'].dt.strftime('%Y-%m-%d'))
    }

    _SM_DATE_MAP = date_map
    _SM_CACHE = df
    print(f"  [小市值Top100] 市值数据已加载: {len(df)}行, {len(date_map)}天")
    return df


def get_signals(data):
    """每月末调仓: 选市值最小的100只"""
    _load_market_cap()
    if _SM_DATE_MAP is None:
        return pd.DataFrame(columns=['symbol', 'weight'])

    trade_date = str(data['trade_date'].iloc[0])[:10]
    symbols = data['symbol'].tolist()

    # 批量获取市值 (前向填充)
    dates = sorted(_SM_DATE_MAP.keys())
    if trade_date < dates[0]:
        return pd.DataFrame(columns=['symbol', 'weight'])
    valid_dates = [d for d in dates if d <= trade_date]
    latest_date = valid_dates[-1] if valid_dates else dates[-1]
    date_mc = _SM_DATE_MAP[latest_date]

    mc_values = []
    valid_symbols = []
    for sym in symbols:
        mc = date_mc.get(sym)
        if mc is not None and mc > 0:
            mc_values.append(mc)
            valid_symbols.append(sym)

    if len(valid_symbols) < 100:
        return pd.DataFrame(columns=['symbol', 'weight'])

    # 选市值最小的100只, 等权持有
    result = pd.DataFrame({'symbol': valid_symbols, 'market_cap': mc_values})
    top100 = result.nsmallest(100, 'market_cap')

    return pd.DataFrame({
        'symbol': top100['symbol'].values,
        'weight': [1.0 / 100] * 100,
    })
