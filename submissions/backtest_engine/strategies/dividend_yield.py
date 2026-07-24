"""
红利策略 — 季度调仓

选股逻辑 (参考雪球文章 十拳剑灵):
  1. 股息率 = 最近12个月现金分红总额 / 总市值
  2. 全A股中筛选股息率最高的股票
  3. 剔除ST/停牌/退市 (引擎自动处理)
  4. 等权买入, 持有到下个季度
  5. 调仓频率: 季度 (约63个交易日)

反转逻辑:
  高股息率 = 股价被低估 → 均值回归 → 自动高抛低吸
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DATA_DIR
import pandas as pd
import numpy as np

STRATEGY_NAME = "红利策略(季)"

# 模块级缓存
_DY_CACHE = None


def _load_div_yield():
    """加载预计算的股息率数据"""
    global _DY_CACHE
    if _DY_CACHE is not None:
        return _DY_CACHE

    path = os.path.join(DATA_DIR, "dividend_yield.parquet")
    if not os.path.exists(path):
        print("  [红利] ⚠️ 股息率数据不存在, 跳过")
        return None

    df = pd.read_parquet(path)
    df['date'] = pd.to_datetime(df['date'])
    print(f"  [红利] 股息率数据已加载: {len(df)} 行, {df['symbol'].nunique()} 只")
    _DY_CACHE = df
    return df


def get_signals(data):
    """季度调仓红利策略"""
    div_df = _load_div_yield()
    if div_df is None:
        return pd.DataFrame(columns=['symbol', 'weight'])

    trade_date = str(data['trade_date'].iloc[0])[:10]
    trade_ts = pd.Timestamp(trade_date)

    symbols = data['symbol'].tolist()

    # 找到 <= trade_date 的最新股息率日期
    dy_dates = sorted(div_df['date'].unique())
    valid = [d for d in dy_dates if d <= trade_ts]
    if not valid:
        return pd.DataFrame(columns=['symbol', 'weight'])

    latest_dy_date = valid[-1]
    dy_slice = div_df[div_df['date'] == latest_dy_date]

    # 对齐到当前可交易股票
    dy_map = dict(zip(dy_slice['symbol'], dy_slice['div_yield']))

    valid_symbols = []
    yields = []
    for sym in symbols:
        dy = dy_map.get(sym)
        if dy is not None and dy > 0:
            valid_symbols.append(sym)
            yields.append(dy)

    if len(valid_symbols) < 20:
        print(f"  [红利] 有效股票不足 ({len(valid_symbols)}), 跳过")
        return pd.DataFrame(columns=['symbol', 'weight'])

    # 按股息率排序, 取前30%
    result = pd.DataFrame({'symbol': valid_symbols, 'div_yield': yields})
    result = result.sort_values('div_yield', ascending=False)

    # 取前30%(最少20只, 最多50只)
    n_top = max(20, min(50, int(len(result) * 0.3)))
    top = result.head(n_top)

    n = len(top)
    return pd.DataFrame({
        'symbol': top['symbol'].values,
        'weight': 1.0 / n,
    })
