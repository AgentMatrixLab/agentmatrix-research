"""
改善版红利策略 v2 — 半年度调仓 + 质量过滤

v1 问题:
  - 年化 3.98%, 超额 -24.89%, 回撤 38.53%
  - 大量持仓是"价值陷阱"(高股息但弱基本面)

v2 改进:
  1. ROE > 5% + 净利润 > 0 (剔除价值陷阱, 确保股息可持续)
  2. 半年度调仓 (126个交易日 ≈ 6个月)
  3. 取前20只高股息 (更集中)

选股逻辑:
  全A股 → 股息率排序 → ROE>5% + 净利润>0 → 
  取前20只高股息 → 等权 → 半年度调仓
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DATA_DIR
import pandas as pd
import numpy as np

STRATEGY_NAME = "红利策略v2(半年)"

# 模块级缓存
_DY_CACHE = None
_FIN_CACHE = None
_FIN_MAP = None  # {symbol: {roe, net_profit}}


def _load_data():
    """加载股息率 + 财务数据"""
    global _DY_CACHE, _FIN_CACHE, _FIN_MAP
    if _DY_CACHE is not None:
        return _DY_CACHE

    # 股息率
    dy_path = os.path.join(DATA_DIR, "dividend_yield.parquet")
    if not os.path.exists(dy_path):
        print("  [红利v2] ⚠️ 股息率数据不存在")
        return None
    dy = pd.read_parquet(dy_path)
    dy['date'] = pd.to_datetime(dy['date'])
    print(f"  [红利v2] 股息率: {len(dy)} 行, {dy['symbol'].nunique()} 只")
    _DY_CACHE = dy

    # 财务数据 (ROE过滤)
    bs_path = os.path.join(DATA_DIR, "balance_sheet.parquet")
    is_path = os.path.join(DATA_DIR, "income_stmt.parquet")
    if os.path.exists(bs_path) and os.path.exists(is_path):
        bs = pd.read_parquet(bs_path)
        inc = pd.read_parquet(is_path)

        # 合并计算ROE
        fin = bs.merge(
            inc[['symbol', 'report_period', 'ann_date', 'net_profit']],
            on=['symbol', 'report_period', 'ann_date'], how='inner', suffixes=('', '_i')
        )
        fin['roe'] = fin['net_profit'] / fin['total_equity'].replace(0, np.nan)

        # 取每只股票最新报告
        fin_latest = fin.sort_values('ann_date').groupby('symbol').last().reset_index()

        # 构建字典: symbol -> {roe, net_profit}
        _FIN_MAP = {}
        for _, row in fin_latest.iterrows():
            _FIN_MAP[row['symbol']] = {
                'roe': row['roe'],
                'net_profit': row['net_profit'],
            }
        print(f"  [红利v2] 财务: {len(_FIN_MAP)} 只")

    return _DY_CACHE


def get_signals(data):
    """半年度调仓红利策略 v2"""
    dy = _load_data()
    if dy is None:
        return pd.DataFrame(columns=['symbol', 'weight'])

    trade_ts = pd.Timestamp(str(data['trade_date'].iloc[0])[:10])
    symbols = data['symbol'].tolist()

    # === 1. 取最新股息率 ===
    dy_dates = sorted(dy['date'].unique())
    valid = [d for d in dy_dates if d <= trade_ts]
    if not valid:
        return pd.DataFrame(columns=['symbol', 'weight'])
    latest_dy_date = valid[-1]
    dy_slice = dy[dy['date'] == latest_dy_date]
    dy_map = dict(zip(dy_slice['symbol'], dy_slice['div_yield']))

    # === 2. 构建候选池: 高股息 + 质量过滤 ===
    candidates = []
    for sym in symbols:
        dy_val = dy_map.get(sym)
        if dy_val is None or dy_val <= 0:
            continue

        # 质量过滤: 用最新可用财报检查ROE和净利润
        if _FIN_MAP and sym in _FIN_MAP:
            info = _FIN_MAP[sym]
            roe = info.get('roe', np.nan)
            np_val = info.get('net_profit', 0)
            if not (not np.isnan(roe) and roe > 0.05 and np_val > 0):
                continue
        # 如果没有财务数据, 仍然保留(放宽条件)
        # 但股息率过低的不考虑
        if dy_val < 0.001:  # 0.1%以下忽略
            continue

        candidates.append({
            'symbol': sym,
            'div_yield': dy_val,
        })

    if len(candidates) < 10:
        return pd.DataFrame(columns=['symbol', 'weight'])

    # === 3. 选前20只高股息 ===
    result = pd.DataFrame(candidates).sort_values('div_yield', ascending=False)
    top = result.head(20)

    n = len(top)
    return pd.DataFrame({
        'symbol': top['symbol'].values,
        'weight': 1.0 / n,
    })
