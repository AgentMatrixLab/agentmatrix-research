"""
v4g — 分红覆盖过滤 (经营现金流>分红金额)

思路: 分红可持续性 = 经营现金流能覆盖分红
      有些公司借钱分红 → 不可持续 → 未来可能降/停分红
      用现金流量表的 net_cash_flows_opera_act 来验证
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DATA_DIR
import pandas as pd
import numpy as np

STRATEGY_NAME = "红利v4g(现金流)"
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
    # 现金流数据 (从cash_flow_tmp解析)
    cf_path = os.path.join(DATA_DIR, "cash_flow_tmp.parquet")
    
    if os.path.exists(bs_path) and os.path.exists(is_path):
        bs = pd.read_parquet(bs_path)
        inc = pd.read_parquet(is_path)
        fin = bs.merge(inc[['symbol','report_period','ann_date','net_profit']],
                       on=['symbol','report_period','ann_date'], how='inner', suffixes=('','_i'))
        fin['roe'] = fin['net_profit'] / fin['total_equity'].replace(0, np.nan)
        
        # 合并现金流数据
        if os.path.exists(cf_path):
            cf = pd.read_parquet(cf_path)
            import json
            cf_records = []
            for _, row in cf.iterrows():
                try:
                    p = json.loads(row['raw_payload']) if isinstance(row['raw_payload'], str) else row['raw_payload']
                    ocf = float(p.get('net_cash_flows_opera_act', 0) or 0)
                    div_paid = float(p.get('CASH_PAY_DIST_DIV_PRO_INT', 0) or 0)
                    cf_records.append({'symbol': row['symbol'], 'report_period': row['report_period'],
                                       'ann_date': row['ann_date'], 'operating_cf': ocf, 'dividend_paid': div_paid})
                except: pass
            if cf_records:
                cf_df = pd.DataFrame(cf_records)
                fin = fin.merge(cf_df[['symbol','report_period','ann_date','operating_cf','dividend_paid']],
                                on=['symbol','report_period','ann_date'], how='left', suffixes=('','_cf'))
                fin['cf_covers_dividend'] = fin['operating_cf'] >= fin['dividend_paid']
        
        fin = fin.sort_values('ann_date').groupby('symbol').last().reset_index()
        _FIN_MAP = {}
        for _, r in fin.iterrows():
            _FIN_MAP[r['symbol']] = {
                'roe': r['roe'], 'net_profit': r['net_profit'],
                'cf_covers_div': r.get('cf_covers_dividend', True),
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
            roe = info['roe']; np_val = info['net_profit']
            if np.isnan(roe) or roe <= 0.05 or np_val <= 0: continue
            if dy_val > 0.15: continue
            # 经营现金流必须能覆盖分红 (避免借钱分红)
            if not info.get('cf_covers_div', True):
                continue
        else:
            continue
        cand.append({'symbol': sym, 'div_yield': dy_val})

    if len(cand) < 15: return pd.DataFrame(columns=['symbol','weight'])
    top = pd.DataFrame(cand).sort_values('div_yield', ascending=False).head(20)
    n = len(top)
    return pd.DataFrame({'symbol': top['symbol'].values, 'weight': 1.0 / n})
