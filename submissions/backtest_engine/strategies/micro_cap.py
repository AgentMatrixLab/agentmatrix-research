"""
微盘股策略 — 每月调仓

选股规则:
  1. 全A股中市值最小的400只股票
  2. 剔除ST/*ST/退市整理/上市首日/首发连扳未打开
  3. 每月末调仓, 等权持有

参考: 米筐微盘股指数 (866006.RI)
"""

import os
import pandas as pd
import numpy as np

STRATEGY_NAME = "微盘股(月)"

# 模块级缓存
_MC_CACHE = None
_MC_DATE_MAP = None  # {date_str: {symbol: market_cap_in_yi}}


def _load_market_cap():
    """加载市值数据并建立快速查找索引"""
    global _MC_CACHE, _MC_DATE_MAP
    if _MC_CACHE is not None:
        return _MC_CACHE

    path = os.path.join(os.path.dirname(__file__), "..", "data", "market_cap_full.parquet")
    if not os.path.exists(path):
        print(f"  [微盘股] ⚠️ 市值数据不存在: {path}")
        return None

    df = pd.read_parquet(path)

    # 构建按日期索引的字典 (用groupby加速)
    print("  构建索引...", end=' ', flush=True)
    df2 = df.reset_index()
    df2['symbol'] = df2['order_book_id'].str.replace('.XSHE', '.SZ').str.replace('.XSHG', '.SH')
    df2['mc_yi'] = df2['market_cap'] / 1e8
    date_map = {
        str(d): dict(zip(grp['symbol'], grp['mc_yi']))
        for d, grp in df2.groupby(df2['date'].dt.strftime('%Y-%m-%d'))
    }
    print(f"{len(date_map)}天")

    _MC_DATE_MAP = date_map
    _MC_CACHE = df
    print(f"  [微盘股] 市值数据已加载: {len(df)}行, {len(date_map)}天")
    return df


def get_signals(data):
    """每日调仓微盘股策略 (市值最小400只, 等权)"""
    # 加载市值数据
    _load_market_cap()
    if _MC_DATE_MAP is None:
        return pd.DataFrame(columns=['symbol', 'weight'])

    trade_date = str(data['trade_date'].iloc[0])[:10]
    symbols = data['symbol'].tolist()

    # 批量获取市值 (前向填充)
    dates = sorted(_MC_DATE_MAP.keys())
    if trade_date < dates[0]:
        return pd.DataFrame(columns=['symbol', 'weight'])
    valid_dates = [d for d in dates if d <= trade_date]
    latest_date = valid_dates[-1] if valid_dates else dates[-1]
    date_mc = _MC_DATE_MAP[latest_date]

    # 为每个symbol获取市值
    mc_values = []
    valid_symbols = []
    for sym in symbols:
        mc = date_mc.get(sym)
        if mc is not None and mc > 0:
            mc_values.append(mc)
            valid_symbols.append(sym)

    if len(valid_symbols) < 400:
        print(f"  [微盘股] ⚠️ 可交易股票不足400只: {len(valid_symbols)}")
        return pd.DataFrame(columns=['symbol', 'weight'])

    # 按市值升序排列, 取最小的400只
    result = pd.DataFrame({'symbol': valid_symbols, 'market_cap': mc_values})
    result = result.sort_values('market_cap').head(400).copy()

    n = len(result)
    return pd.DataFrame({
        'symbol': result['symbol'].values,
        'weight': 1.0 / n,
    })
