"""
v4a — 缓冲区调仓 (降低换手)

思路: 
  v2的42%换手已不高, 但仍有优化空间
  缓冲区: 持仓只要还在股息率前30名就留着, 只换掉掉出前30的
  效果: 减少不必要的买卖, 降低成本
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DATA_DIR
import pandas as pd
import numpy as np

STRATEGY_NAME = "红利v4a(缓冲区)"
_DY_CACHE = None
_FIN_MAP = None
_PREV = None


def _load_data():
    global _DY_CACHE, _FIN_MAP
    if _DY_CACHE is not None:
        return _DY_CACHE
    path = os.path.join(DATA_DIR, "dividend_yield.parquet")
    dy = pd.read_parquet(path)
    dy['date'] = pd.to_datetime(dy['date'])
    _DY_CACHE = dy

    bs_path = os.path.join(DATA_DIR, "balance_sheet.parquet")
    is_path = os.path.join(DATA_DIR, "income_stmt.parquet")
    if os.path.exists(bs_path) and os.path.exists(is_path):
        bs = pd.read_parquet(bs_path)
        inc = pd.read_parquet(is_path)
        fin = bs.merge(inc[['symbol','report_period','ann_date','net_profit']],
                       on=['symbol','report_period','ann_date'], how='inner', suffixes=('','_i'))
        fin['roe'] = fin['net_profit'] / fin['total_equity'].replace(0, np.nan)
        fin = fin.sort_values('ann_date').groupby('symbol').last().reset_index()
        _FIN_MAP = {}
        for _, r in fin.iterrows():
            _FIN_MAP[r['symbol']] = {'roe': r['roe'], 'net_profit': r['net_profit']}
    return _DY_CACHE


def get_signals(data):
    global _PREV
    dy = _load_data()
    if dy is None:
        return pd.DataFrame(columns=['symbol','weight'])

    trade_ts = pd.Timestamp(str(data['trade_date'].iloc[0])[:10])
    symbols = data['symbol'].tolist()

    dy_dates = sorted(dy['date'].unique())
    valid = [d for d in dy_dates if d <= trade_ts]
    if not valid:
        return pd.DataFrame(columns=['symbol','weight'])
    dy_slice = dy[dy['date'] == valid[-1]]
    dy_map = dict(zip(dy_slice['symbol'], dy_slice['div_yield']))

    cand = []
    for sym in symbols:
        dy_val = dy_map.get(sym)
        if dy_val is None or dy_val <= 0:
            continue
        if _FIN_MAP and sym in _FIN_MAP:
            info = _FIN_MAP[sym]
            roe = info['roe']; np_val = info['net_profit']
            if np.isnan(roe) or roe <= 0.05 or np_val <= 0:
                continue
            if dy_val > 0.15:
                continue
        else:
            continue
        cand.append({'symbol': sym, 'div_yield': dy_val})

    if len(cand) < 15:
        return pd.DataFrame(columns=['symbol','weight'])
    
    df = pd.DataFrame(cand).sort_values('div_yield', ascending=False)
    
    # === 缓冲区逻辑 ===
    top30_symbols = set(df.head(30)['symbol'].values)
    top20 = df.head(20)['symbol'].tolist()
    
    if _PREV is not None:
        # 保留上一期持仓中还在前30的
        keep = [s for s in _PREV if s in top30_symbols]
        # 新面孔：前20中不在keep里的
        new = [s for s in top20 if s not in keep]
        # 补齐到20只
        final = (keep + new)[:20]
    else:
        final = top20
    
    _PREV = set(final)
    n = len(final)
    return pd.DataFrame({'symbol': final, 'weight': 1.0 / n})
