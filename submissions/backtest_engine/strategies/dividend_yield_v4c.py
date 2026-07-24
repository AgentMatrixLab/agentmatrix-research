"""
v4c — 盈利增长过滤 (排除利润下滑)

思路:
  v2只看净利润>0, 但利润下滑的公司未来可能降分红
  加: 净利润同比增长 > -20% (同比不能太差)
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DATA_DIR
import pandas as pd
import numpy as np

STRATEGY_NAME = "红利v4c(增长过滤)"
_DY_CACHE = None
_FIN_MAP = None  # {symbol: {roe, np, np_yoy}}


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
        
        # 计算净利润同比增长率 (同一symbol, 上一期report_period)
        fin = fin.sort_values(['symbol', 'report_period'])
        fin['np_prev'] = fin.groupby('symbol')['net_profit'].shift(1)
        fin['np_yoy'] = (fin['net_profit'] - fin['np_prev']) / fin['np_prev'].replace(0, np.nan).abs() * -1
        
        # 取最新
        fin = fin.groupby('symbol').last().reset_index()
        
        _FIN_MAP = {}
        for _, r in fin.iterrows():
            _FIN_MAP[r['symbol']] = {
                'roe': r['roe'], 'net_profit': r['net_profit'],
                'np_yoy': r.get('np_yoy', np.nan)
            }
    return _DY_CACHE


def get_signals(data):
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
            # v4c新增: 净利润同比不能下滑超过20%
            np_yoy = info.get('np_yoy', np.nan)
            if not np.isnan(np_yoy) and np_yoy < -0.20:
                continue
            if dy_val > 0.15:
                continue
        else:
            continue
        cand.append({'symbol': sym, 'div_yield': dy_val})

    if len(cand) < 15:
        return pd.DataFrame(columns=['symbol','weight'])
    
    top = pd.DataFrame(cand).sort_values('div_yield', ascending=False).head(20)
    n = len(top)
    return pd.DataFrame({'symbol': top['symbol'].values, 'weight': 1.0 / n})
