"""
红利策略 v7 — PIT版 (Point-in-Time 财务数据)

v6 -> v7 变更:
  - 财务数据改为PIT: 按 ann_date <= trade_date 取已披露报告
  - 解决2019年非PIT导致的误杀问题 (groupby.last拿到2024数据)
  - 选股逻辑不变: ROE>5% + 净利润>0 + DY>0 + 排除增长>20% + 前20只
"""
import os, sys, glob
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DATA_DIR
import pandas as pd
import numpy as np

STRATEGY_NAME = "红利策略v7(PIT对齐)"
_DY_CACHE = None
_FIN_RAW = None       # PIT: 原始财务DataFrame, 不做预聚合
_FIN_CACHE = {}       # {trade_date_str: {symbol: {roe, net_profit, np_growth}}}


def _load_data():
    global _DY_CACHE, _FIN_RAW
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

    # === PIT财务: 加载原始数据, 不在模块级聚合 ===
    bs_path = os.path.join(DATA_DIR, "balance_sheet.parquet")
    is_path = os.path.join(DATA_DIR, "income_stmt.parquet")

    if os.path.exists(bs_path) and os.path.exists(is_path):
        bs = pd.read_parquet(bs_path)
        inc = pd.read_parquet(is_path)
        fin = bs.merge(inc[['symbol', 'report_period', 'ann_date', 'net_profit']],
                       on=['symbol', 'report_period', 'ann_date'], how='inner', suffixes=('', '_i'))
        fin['roe'] = fin['net_profit'] / fin['total_equity'].replace(0, np.nan)
        # 按 symbol + report_period 排序, 方便PIT查询
        fin = fin.sort_values(['symbol', 'report_period']).reset_index(drop=True)
        _FIN_RAW = fin

    return _DY_CACHE


def _get_fin_map_pit(trade_ts):
    """PIT: 获取截至 trade_ts 已披露的最新财务数据"""
    global _FIN_CACHE, _FIN_RAW

    ts_key = str(trade_ts.date())
    if ts_key in _FIN_CACHE:
        return _FIN_CACHE[ts_key]

    if _FIN_RAW is None:
        _FIN_CACHE[ts_key] = None
        return None

    # 过滤: 只取ann_date <= trade_ts的报告
    fin_pit = _FIN_RAW[_FIN_RAW['ann_date'] <= trade_ts].copy()

    use_first = False
    if len(fin_pit) == 0:
        # trade_date早于第一份财报公告日 → 用最早可用报告
        fin_pit = _FIN_RAW.copy()
        use_first = True

    if len(fin_pit) == 0:
        _FIN_CACHE[ts_key] = None
        return None

    # 按symbol取最新(or最早)report_period
    if use_first:
        fin_latest = fin_pit.groupby('symbol', sort=False).first().reset_index()
    else:
        fin_latest = fin_pit.groupby('symbol', sort=False).last().reset_index()

    # PIT np_growth: 在fin_pit中计算
    fin_pit['np_prev'] = fin_pit.groupby('symbol')['net_profit'].shift(1)
    prev_abs = fin_pit['np_prev'].replace(0, np.nan).abs()
    fin_pit['np_growth'] = (fin_pit['net_profit'] - fin_pit['np_prev']) / prev_abs

    # 取对应条的增长数据
    if use_first:
        fin_latest_growth = fin_pit.groupby('symbol', sort=False).first().reset_index()
    else:
        fin_latest_growth = fin_pit.groupby('symbol', sort=False).last().reset_index()
    fin_latest = fin_latest.merge(
        fin_latest_growth[['symbol', 'report_period', 'np_growth']],
        on=['symbol', 'report_period'], how='left'
    )

    result = {}
    for _, r in fin_latest.iterrows():
        result[r['symbol']] = {
            'roe': r['roe'],
            'net_profit': r['net_profit'],
            'np_growth': r.get('np_growth', np.nan)
        }

    _FIN_CACHE[ts_key] = result
    return result


def get_signals(data):
    dy = _load_data()
    if dy is None:
        return pd.DataFrame(columns=['symbol', 'weight'])

    # K线symbol格式转换
    symbols_raw = data['symbol'].tolist()
    symbol_conv = {}
    for s in symbols_raw:
        cs = s.replace('.XSHE', '.SZ').replace('.XSHG', '.SH')
        symbol_conv[cs] = s

    symbols = list(symbol_conv.keys())
    trade_ts = pd.Timestamp(str(data['trade_date'].iloc[0])[:10])

    # 股息率
    dy_dates = sorted(dy['date'].unique())
    valid = [d for d in dy_dates if d <= trade_ts]
    if not valid:
        return pd.DataFrame(columns=['symbol', 'weight'])
    dy_slice = dy[dy['date'] == valid[-1]]
    dy_map = dict(zip(dy_slice['symbol'], dy_slice['div_yield']))

    # PIT财务
    fin_map = _get_fin_map_pit(trade_ts)

    cand = []
    for sym in symbols:
        dy_val = dy_map.get(sym)
        if dy_val is None or dy_val <= 0:
            continue

        if fin_map and sym in fin_map:
            info = fin_map[sym]
            roe = info['roe']
            np_val = info['net_profit']
            np_g = info.get('np_growth', np.nan)
            if np.isnan(roe) or roe <= 0.05 or np_val <= 0:
                continue
            if dy_val > 0.15:
                continue
            if not np.isnan(np_g) and np_g > 0.20:
                continue
        elif fin_map is None:
            # 无财务数据 → 只靠股息率筛选 (无ROE/利润过滤)
            if dy_val > 0.15:
                continue
        else:
            # 有财务地图但该股票不在其中
            continue

        cand.append({'symbol': sym, 'div_yield': dy_val})

    if len(cand) < 5:
        return pd.DataFrame(columns=['symbol', 'weight'])
    top = pd.DataFrame(cand).sort_values('div_yield', ascending=False).head(20)
    n = len(top)
    return pd.DataFrame({'symbol': top['symbol'].values, 'weight': 1.0 / n})
