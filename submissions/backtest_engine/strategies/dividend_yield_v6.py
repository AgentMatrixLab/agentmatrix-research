"""
红利策略 v6 — 对齐聚宽版 (非PIT, groupby symbol last)

v5 -> v6 变更:
  1. 股息率: 按负债率扣除利息 (对齐聚宽 STK_XR_XD 口径)
  2. 调仓: 改为每年1月/7月首个交易日 (对齐聚宽 run_monthly)
  3. 选股逻辑不变: ROE>5% + 净利润>0 + 排除增长>20% + 前20只

数据适配:
  - 股息率: 读取逐年文件 dividend_yield_20*.parquet
  - 财务: balance_sheet.parquet + income_stmt.parquet, groupby(symbol).last()
"""
import os, sys, glob
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DATA_DIR
import pandas as pd
import numpy as np

STRATEGY_NAME = "红利策略v6(聚宽对齐)"
_DY_CACHE = None
_FIN_MAP = None


def _load_data():
    global _DY_CACHE, _FIN_MAP
    if _DY_CACHE is not None:
        return _DY_CACHE
    
    # === 股息率: 读取逐年文件 ===
    div_files = sorted(glob.glob(os.path.join(DATA_DIR, "dividend_yield_20*.parquet")))
    if div_files:
        parts = []
        for f in div_files:
            df = pd.read_parquet(f)
            col_map = {}
            if 'order_book_id' in df.columns:
                col_map['order_book_id'] = 'symbol'
            if 'dividend_yield' in df.columns:
                col_map['dividend_yield'] = 'div_yield'
            df = df.rename(columns=col_map)
            if 'symbol' in df.columns:
                df['symbol'] = df['symbol'].str.replace('.XSHE', '.SZ', regex=False)
                df['symbol'] = df['symbol'].str.replace('.XSHG', '.SH', regex=False)
            df['date'] = pd.to_datetime(df['date'])
            parts.append(df)
        dy = pd.concat(parts, ignore_index=True, copy=False)
        del parts
        
        # RQData返回百分比(e.g. 3.5=3.5%), 转小数(0.035)
        if 'div_yield' in dy.columns and dy['div_yield'].median() > 1:
            dy['div_yield'] = dy['div_yield'] / 100.0
        
        _DY_CACHE = dy
    elif os.path.exists(os.path.join(DATA_DIR, "dividend_yield_v2.parquet")):
        dy = pd.read_parquet(os.path.join(DATA_DIR, "dividend_yield_v2.parquet"))
        dy['date'] = pd.to_datetime(dy['date'])
        _DY_CACHE = dy
    elif os.path.exists(os.path.join(DATA_DIR, "dividend_yield.parquet")):
        dy = pd.read_parquet(os.path.join(DATA_DIR, "dividend_yield.parquet"))
        dy['date'] = pd.to_datetime(dy['date'])
        _DY_CACHE = dy

    # === 财务数据: balance_sheet + income_stmt, 非PIT ===
    bs_path = os.path.join(DATA_DIR, "balance_sheet.parquet")
    is_path = os.path.join(DATA_DIR, "income_stmt.parquet")
    
    if os.path.exists(bs_path) and os.path.exists(is_path):
        bs = pd.read_parquet(bs_path)
        inc = pd.read_parquet(is_path)
        fin = bs.merge(inc[['symbol','report_period','ann_date','net_profit']],
                       on=['symbol','report_period','ann_date'], how='inner', suffixes=('','_i'))
        fin['roe'] = fin['net_profit'] / fin['total_equity'].replace(0, np.nan)
        # 计算环比增长
        fin = fin.sort_values(['symbol', 'report_period'])
        fin['np_prev'] = fin.groupby('symbol')['net_profit'].shift(1)
        prev_abs = fin['np_prev'].replace(0, np.nan).abs()
        fin['np_growth'] = (fin['net_profit'] - fin['np_prev']) / prev_abs
        # 非PIT: 每只股票取最新一条
        fin = fin.groupby('symbol').last().reset_index()
        _FIN_MAP = {}
        for _, r in fin.iterrows():
            _FIN_MAP[r['symbol']] = {
                'roe': r['roe'],
                'net_profit': r['net_profit'],
                'np_growth': r.get('np_growth', np.nan)
            }
    
    return _DY_CACHE


def get_signals(data):
    dy = _load_data()
    if dy is None:
        return pd.DataFrame(columns=['symbol','weight'])

    # K线symbol格式: XSHE/XSHG → SZ/SH (对齐财务+股息率)
    symbols_raw = data['symbol'].tolist()
    symbol_conv = {}
    for s in symbols_raw:
        cs = s.replace('.XSHE', '.SZ').replace('.XSHG', '.SH')
        symbol_conv[cs] = s  # 反向映射: converted → original
    
    symbols = list(symbol_conv.keys())
    
    trade_ts = pd.Timestamp(str(data['trade_date'].iloc[0])[:10])
    # 股息率
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
            if dy_val > 0.15: continue  # 异常值
            # 排除利润增长>20%
            if not np.isnan(np_g) and np_g > 0.20: continue
        else:
            continue  # 无财务数据, 直接排除
        
        cand.append({'symbol': sym, 'div_yield': dy_val})

    if len(cand) < 5: return pd.DataFrame(columns=['symbol','weight'])
    top = pd.DataFrame(cand).sort_values('div_yield', ascending=False).head(20)
    n = len(top)
    return pd.DataFrame({'symbol': top['symbol'].values, 'weight': 1.0 / n})
