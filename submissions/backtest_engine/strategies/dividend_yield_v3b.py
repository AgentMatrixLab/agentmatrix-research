"""
红利策略 v3b — v2基础上加安全补丁

v2: 年化8.85%, 夏普0.44, 回撤-19.52%, 胜率78.95%
v3(过度): 加了行业分散+波动过滤, 反而退步

v3b:
  1. 保留v2全部条件 (ROE>5%, 净利润>0, 前20只, 半年度)
  2. 加: 负债率<85% (剔除极端高杠杆, 但银行等可保留)
  3. 加: 个股最大权重≤10% (防单只黑天鹅, 默认20只=5%不受影响)
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DATA_DIR
import pandas as pd
import numpy as np

STRATEGY_NAME = "红利策略v3b(半年)"

_DY_CACHE = None
_FIN_MAP = None


def _load_data():
    global _DY_CACHE, _FIN_MAP
    if _DY_CACHE is not None:
        return _DY_CACHE

    # 股息率
    path = os.path.join(DATA_DIR, "dividend_yield.parquet")
    if not os.path.exists(path):
        return None
    dy = pd.read_parquet(path)
    dy['date'] = pd.to_datetime(dy['date'])
    print(f"  [v3b] 股息率: {len(dy)} 行")
    _DY_CACHE = dy

    # 财务
    bs_path = os.path.join(DATA_DIR, "balance_sheet.parquet")
    is_path = os.path.join(DATA_DIR, "income_stmt.parquet")
    if os.path.exists(bs_path) and os.path.exists(is_path):
        bs = pd.read_parquet(bs_path)
        inc = pd.read_parquet(is_path)
        fin = bs.merge(
            inc[['symbol', 'report_period', 'ann_date', 'net_profit']],
            on=['symbol', 'report_period', 'ann_date'], how='inner', suffixes=('', '_i')
        )
        fin['roe'] = fin['net_profit'] / fin['total_equity'].replace(0, np.nan)
        fin['debt_ratio'] = fin['total_liabilities'] / fin['total_assets'].replace(0, np.nan)
        fin_latest = fin.sort_values('ann_date').groupby('symbol').last().reset_index()

        _FIN_MAP = {}
        for _, row in fin_latest.iterrows():
            _FIN_MAP[row['symbol']] = {
                'roe': row['roe'],
                'net_profit': row['net_profit'],
                'debt_ratio': row['debt_ratio'],
            }
        print(f"  [v3b] 财务: {len(_FIN_MAP)} 只")

    return _DY_CACHE


def get_signals(data):
    dy = _load_data()
    if dy is None:
        return pd.DataFrame(columns=['symbol', 'weight'])

    trade_ts = pd.Timestamp(str(data['trade_date'].iloc[0])[:10])
    symbols = data['symbol'].tolist()

    # 股息率
    dy_dates = sorted(dy['date'].unique())
    valid = [d for d in dy_dates if d <= trade_ts]
    if not valid:
        return pd.DataFrame(columns=['symbol', 'weight'])
    dy_slice = dy[dy['date'] == valid[-1]]
    dy_map = dict(zip(dy_slice['symbol'], dy_slice['div_yield']))

    # 候选池
    candidates = []
    for sym in symbols:
        dy_val = dy_map.get(sym)
        if dy_val is None or dy_val <= 0:
            continue

        if _FIN_MAP and sym in _FIN_MAP:
            info = _FIN_MAP[sym]
            roe = info.get('roe', np.nan)
            np_val = info.get('net_profit', 0)
            debt = info.get('debt_ratio', np.nan)

            # v2 条件: ROE>5%, 净利润>0
            if np.isnan(roe) or roe <= 0.05 or np_val <= 0:
                continue
            # v3b 新增: 负债率<85% (保留银行但剔除极端高杠杆)
            if not np.isnan(debt) and debt >= 0.85:
                continue
            # 股息率异常过滤
            if dy_val > 0.15:
                continue
        else:
            continue

        candidates.append({'symbol': sym, 'div_yield': dy_val})

    if len(candidates) < 15:
        return pd.DataFrame(columns=['symbol', 'weight'])

    # 按股息率排序取前20
    df = pd.DataFrame(candidates).sort_values('div_yield', ascending=False)
    top = df.head(20)

    # 个股最大权重≤10% (默认20只=5%, 但如果少于10只则控制在10%)
    n = len(top)
    weights = np.full(n, 1.0 / n)
    # 如果少于10只, 限制每只不超过10%
    if n < 10:
        weights = np.full(n, min(1.0 / n, 0.10))
        weights = weights / weights.sum()

    return pd.DataFrame({
        'symbol': top['symbol'].values,
        'weight': weights,
    })
