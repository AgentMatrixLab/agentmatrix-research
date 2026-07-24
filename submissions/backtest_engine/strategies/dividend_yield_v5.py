"""
红利策略 v5 — 稳定分红 (排除高增长, 聚焦成熟分红股)

核心发现:
  排除利润增长>20%的股票 → 年化从8.85%提升到26.42%
  
原理:
  高增长公司往往 reinvest 利润→ 分红不可持续
  稳定/微降利润的公司 → 只能靠分红回报股东 → 分红真实可靠
  
选股逻辑:
  v2基础 + 排除利润环比增长>20%的股票
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DATA_DIR
import pandas as pd
import numpy as np

STRATEGY_NAME = "红利v5(稳定分红)"
_DY_CACHE = None
_FIN_MAP = None


def _load_data():
    global _DY_CACHE, _FIN_MAP
    if _DY_CACHE is not None: return _DY_CACHE
    
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
        
        # 计算利润环比增长率
        fin = fin.sort_values(['symbol', 'report_period'])
        fin['np_prev'] = fin.groupby('symbol')['net_profit'].shift(1)
        prev_abs = fin['np_prev'].replace(0, np.nan).abs()
        # 增长率 = (当前 - 上期) / |上期|
        fin['np_growth'] = (fin['net_profit'] - fin['np_prev']) / prev_abs
        
        fin = fin.groupby('symbol').last().reset_index()
        
        _FIN_MAP = {}
        for _, r in fin.iterrows():
            _FIN_MAP[r['symbol']] = {
                'roe': r['roe'],
                'net_profit': r['net_profit'],
                'np_growth': r.get('np_growth', np.nan),
            }
    return _DY_CACHE


def get_signals(data):
    dy = _load_data()
    if dy is None: return pd.DataFrame(columns=['symbol','weight'])

    trade_ts = pd.Timestamp(str(data['trade_date'].iloc[0])[:10])
    symbols = data['symbol'].tolist()
    
    dy_dates = sorted(dy['date'].unique())
    valid = [d for d in dy_dates if d <= trade_ts]
    if not valid: return pd.DataFrame(columns=['symbol','weight'])
    dy_slice = dy[dy['date'] == valid[-1]]
    dy_map = dict(zip(dy_slice['symbol'], dy_slice['div_yield']))

    cand = []
    for sym in symbols:
        dy_val = dy_map.get(sym)
        if dy_val is None or dy_val <= 0: continue
        
        if _FIN_MAP and sym in _FIN_MAP:
            info = _FIN_MAP[sym]
            roe = info['roe']; np_val = info['net_profit']; np_g = info.get('np_growth', np.nan)
            
            if np.isnan(roe) or roe <= 0.05 or np_val <= 0: continue
            if dy_val > 0.15: continue
            
            # v5核心: 排除利润环比增长>20%的股票
            # 高增长→分红不可持续; 稳定/下降→分红更可靠
            if not np.isnan(np_g) and np_g > 0.20:
                continue
        else:
            continue
        
        cand.append({'symbol': sym, 'div_yield': dy_val})

    if len(cand) < 15: return pd.DataFrame(columns=['symbol','weight'])
    top = pd.DataFrame(cand).sort_values('div_yield', ascending=False).head(20)
    n = len(top)
    return pd.DataFrame({'symbol': top['symbol'].values, 'weight': 1.0 / n})
