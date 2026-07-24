"""
小市值策略 — 每月调仓

选股规则:
  1. 全A股中市值 < 100亿的股票
  2. 剔除ST/停牌
  3. 等权买入, 持有到下个月末

数据源: market_cap_full.parquet (RQData, 2017-2025)
"""
import os
import pandas as pd
import numpy as np

STRATEGY_NAME = "小市值(月)"

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
        print("  [小市值] ⚠️ 市值数据不存在")
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
    print(f"  [小市值] 市值数据已加载: {len(df)}行, {len(date_map)}天")
    return df


def _get_mc(date_str, symbol):
    """获取单只股票的市值(亿元), 返回NaN如果没有数据"""
    dates = sorted(_MC_DATE_MAP.keys())
    if not dates:
        return np.nan
    # 找到 <= date_str 的最新日期, 如果date_str更新就用最后一个
    valid = [d for d in dates if d <= date_str]
    if not valid:
        # 如果date_str在所有数据之前, 用第一个
        latest_date = dates[0]
    else:
        latest_date = valid[-1]
    return _MC_DATE_MAP[latest_date].get(symbol, np.nan)


def get_signals(data):
    """每月末调仓小市值策略"""
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

    if len(valid_symbols) < 100:
        return pd.DataFrame(columns=['symbol', 'weight'])

    # 市值 < 100亿, 等权持有
    result = pd.DataFrame({'symbol': valid_symbols, 'market_cap': mc_values})
    small = result[result['market_cap'] < 100].copy()

    if len(small) < 20:
        return pd.DataFrame(columns=['symbol', 'weight'])

    n = len(small)
    return pd.DataFrame({
        'symbol': small['symbol'].values,
        'weight': 1.0 / n,
    })
