"""
Barra 四因子每日调仓策略

因子:
  1. BP = total_equity / total_assets
  2. EY = net_profit / total_assets  
  3. Lev = -total_liabilities / total_assets
  4. NLS = size² 对 size 回归残差

选股: 等权复合评分 → Top 20% → 等权持仓
"""
STRATEGY_NAME = "Barra四因子"

import os
import pandas as pd
import numpy as np

# 模块级缓存 (一次加载, 多次查询)
_FIN_CACHE = None  # DataFrame: all financial data sorted
_FIN_LOOKUP = None  # dict: {symbol: (sorted_periods_array, sorted_values_array)}


def _load_and_prep(data_dir):
    """加载财务数据并构建快速查找索引"""
    global _FIN_CACHE, _FIN_LOOKUP
    if _FIN_CACHE is not None:
        return _FIN_CACHE

    path_bs = os.path.join(data_dir, "balance_sheet.parquet")
    path_is = os.path.join(data_dir, "income_stmt.parquet")
    if not os.path.exists(path_bs) or not os.path.exists(path_is):
        print("  [Barra] ⚠️ 无财务数据")
        return None

    bs = pd.read_parquet(path_bs)
    inc = pd.read_parquet(path_is)
    inc = inc[['symbol', 'report_period', 'net_profit', 'revenue']]

    fin = bs.merge(inc, on=['symbol', 'report_period'], how='left')
    fin['report_period'] = pd.to_datetime(fin['report_period'])

    cols = ['symbol', 'report_period', 'total_assets', 'total_liabilities',
            'total_equity', 'net_profit']
    fin = fin[cols].sort_values(['symbol', 'report_period'])

    # 构建快速查找索引: 每个symbol一个排序好的列表
    lookup = {}
    for sym, grp in fin.groupby('symbol'):
        periods = grp['report_period'].values
        values = grp[['total_assets', 'total_liabilities', 'total_equity', 'net_profit']].values
        lookup[sym] = (periods, values)

    _FIN_CACHE = fin
    _FIN_LOOKUP = lookup
    print(f"  [Barra] 财务数据已加载: {len(fin)} 行, {len(lookup)} 只")
    return fin


def _get_financial_fast(lookup, trade_date, symbols):
    """
    对给定日期和股票列表, 快速获取最新财务数据
    使用预构建的排序索引 + np.searchsorted (二分查找)
    """
    t = np.datetime64(pd.Timestamp(trade_date).to_datetime64())
    results = []

    for sym in symbols:
        if sym not in lookup:
            continue
        periods, values = lookup[sym]
        # 二分查找: 找到最后一个 report_period <= t 的位置
        idx = np.searchsorted(periods, t, side='right') - 1
        if idx < 0:
            continue
        results.append([sym] + list(values[idx]))

    if not results:
        return pd.DataFrame(columns=['symbol', 'total_assets', 'total_liabilities',
                                      'total_equity', 'net_profit'])
    cols = ['symbol', 'total_assets', 'total_liabilities', 'total_equity', 'net_profit']
    return pd.DataFrame(results, columns=cols)


def get_signals(data):
    """Barra 4-factor daily rebalancing strategy"""
    try:
        from config import DATA_DIR
        fin = _load_and_prep(DATA_DIR)
    except ImportError:
        return pd.DataFrame(columns=['symbol', 'weight'])

    if fin is None or _FIN_LOOKUP is None:
        return pd.DataFrame(columns=['symbol', 'weight'])

    trade_date = data['trade_date'].iloc[0]
    symbols = data['symbol'].tolist()

    # 快速二分查找
    fin_today = _get_financial_fast(_FIN_LOOKUP, trade_date, symbols)
    if len(fin_today) < 50:
        return pd.DataFrame(columns=['symbol', 'weight'])

    # 合并到选股池
    df = data.merge(fin_today, on='symbol', how='inner')
    if len(df) < 50:
        return pd.DataFrame(columns=['symbol', 'weight'])

    # ── 计算因子 ──
    total_assets = df['total_assets'].clip(lower=1)

    df['BP'] = df['total_equity'] / total_assets
    df['EY'] = df['net_profit'].fillna(0) / total_assets
    df['Lev'] = -df['total_liabilities'] / total_assets

    size = np.log(total_assets.clip(lower=1e6))
    size2 = size ** 2
    A = np.column_stack([np.ones(len(df)), size.values])
    coeff, _, _, _ = np.linalg.lstsq(A, size2.values, rcond=None)
    df['NLS'] = size2 - A @ coeff

    # ── 标准化 ──
    factor_names = ['BP', 'EY', 'NLS', 'Lev']
    df['score'] = 0.0

    for col in factor_names:
        lo = df[col].quantile(0.05)
        hi = df[col].quantile(0.95)
        vals = df[col].clip(lo, hi)
        mu = vals.mean()
        std = vals.std()
        z = (vals - mu) / std if std > 1e-12 else 0.0
        df['score'] += 0.25 * z

    # ── 选股 Top 20% ──
    df = df.sort_values('score', ascending=False)
    n_select = max(1, int(len(df) * 0.20))
    top = df.iloc[:n_select]

    return pd.DataFrame({
        'symbol': top['symbol'].values,
        'weight': 1.0 / n_select,
    })
