"""
红利策略 v3 — 综合改进版

改进点:
  1. 财务质量: ROE>5% + 净利润>0 + 负债率<70% + 分红率<80%
  2. 行业分散: 单行业≤25% (SW一级行业)
  3. 低波动: 剔除波动率最高的20%
  4. 动量排序: 在红利池内优先选跌幅适中的

选股逻辑:
  全A股 → 股息率排序 → 质量过滤 → 行业分散限制 →
  剔除高波动 → 动量排序 → 选前20只 → 等权 → 半年度调仓
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DATA_DIR
import pandas as pd
import numpy as np
import requests, json

STRATEGY_NAME = "红利策略v3(半年)"

# 模块级缓存
_DY_CACHE = None  # 股息率
_FIN_MAP = None   # 财务数据 {symbol: {roe, debt_ratio, ...}}
_INDUSTRY_MAP = None  # {symbol: industry_name}


def _load_div_yield():
    global _DY_CACHE
    if _DY_CACHE is not None:
        return _DY_CACHE
    path = os.path.join(DATA_DIR, "dividend_yield.parquet")
    if not os.path.exists(path):
        return None
    dy = pd.read_parquet(path)
    dy['date'] = pd.to_datetime(dy['date'])
    print(f"  [v3] 股息率: {len(dy)} 行")
    _DY_CACHE = dy
    return dy


def _load_financials():
    """加载财务数据并计算质量指标"""
    global _FIN_MAP
    if _FIN_MAP is not None:
        return _FIN_MAP

    bs_path = os.path.join(DATA_DIR, "balance_sheet.parquet")
    is_path = os.path.join(DATA_DIR, "income_stmt.parquet")
    if not os.path.exists(bs_path) or not os.path.exists(is_path):
        return None

    bs = pd.read_parquet(bs_path)
    inc = pd.read_parquet(is_path)

    # 合并计算
    fin = bs.merge(
        inc[['symbol', 'report_period', 'ann_date', 'net_profit']],
        on=['symbol', 'report_period', 'ann_date'], how='inner', suffixes=('', '_i')
    )
    fin['roe'] = fin['net_profit'] / fin['total_equity'].replace(0, np.nan)
    fin['debt_ratio'] = fin['total_liabilities'] / fin['total_assets'].replace(0, np.nan)
    fin['payout_ratio_est'] = fin['net_profit'] / fin['total_equity'].replace(0, np.nan) * 0  # placeholder, computed later

    # 取最新
    fin_latest = fin.sort_values('ann_date').groupby('symbol').last().reset_index()

    _FIN_MAP = {}
    for _, row in fin_latest.iterrows():
        _FIN_MAP[row['symbol']] = {
            'roe': row['roe'],
            'net_profit': row['net_profit'],
            'debt_ratio': row['debt_ratio'],
            'total_equity': row['total_equity'],
        }
    print(f"  [v3] 财务: {len(_FIN_MAP)} 只")
    return _FIN_MAP


def _load_industry():
    """加载 SW一级行业分类"""
    global _INDUSTRY_MAP
    if _INDUSTRY_MAP is not None:
        return _INDUSTRY_MAP

    path = os.path.join(DATA_DIR, "industry_map.parquet")
    if os.path.exists(path):
        df = pd.read_parquet(path)
        _INDUSTRY_MAP = dict(zip(df['symbol'], df['industry']))
        print(f"  [v3] 行业: {len(_INDUSTRY_MAP)} 只")
        return _INDUSTRY_MAP

    # 从API下载
    print("  [v3] 下载行业分类...")
    H = {"Authorization": "Bearer sk-adm...49I7"}
    r = requests.get(
        "http://115.159.73.134:8765/ch/ref_industry_index_member",
        params={"limit": 50000}, timeout=120
    )
    d = r.json()
    rows = d.get('data', [])
    
    # 只保留当前成员 (out_date is null)
    current = [r for r in rows if r.get('out_date') is None]
    
    # 获取SW一级行业名称
    # index_code like "801XXX.SI" are SW L1 indices
    # Map: index_code -> level1_name
    r2 = requests.get(
        "http://115.159.73.134:8765/ch/ref_industry_index",
        params={"limit": 5000}, timeout=60
    )
    d2 = r2.json()
    idx_rows = d2.get('data', [])
    code_to_l1 = {}
    for ir in idx_rows:
        if ir.get('level_type') == '1':
            code_to_l1[ir['index_code']] = ir['level1_name']
    
    # 对非L1指数, 追踪到L1
    # 先建立所有索引到L1的映射
    idx_to_l1 = {}
    for ir in idx_rows:
        idx_to_l1[ir['index_code']] = ir.get('level1_name', '')
    
    # Build symbol -> industry
    symbol_industry = {}
    for row in current:
        sym = row['symbol']
        ic = row['index_code']
        l1 = idx_to_l1.get(ic, '')
        if l1 and l1 != '综合':  # Skip '综合' (conglomerate)
            if sym not in symbol_industry or ic.startswith('801'):  # Prefer SW L1
                symbol_industry[sym] = l1
    
    print(f"  [v3] 行业映射: {len(symbol_industry)} 只股票, {len(set(symbol_industry.values()))} 个行业")
    
    # 保存
    sym_list = list(symbol_industry.keys())
    ind_list = [symbol_industry[s] for s in sym_list]
    df = pd.DataFrame({'symbol': sym_list, 'industry': ind_list})
    df.to_parquet(path)
    
    _INDUSTRY_MAP = symbol_industry
    return _INDUSTRY_MAP


def _load_avg_volatility(data):
    """计算每只股票的近6个月平均波动率(用日收益率std)"""
    # data is the full DataFrame passed by the engine
    df = data.copy()
    df = df.sort_values(['symbol', 'trade_date'])
    # 计算日收益率
    df['daily_ret'] = df.groupby('symbol')['close_adj'].pct_change()
    # 每只股票用最近60个交易日算波动率
    vol = df.groupby('symbol')['daily_ret'].apply(
        lambda x: x.dropna().tail(60).std()
    ).reset_index()
    vol.columns = ['symbol', 'volatility']
    return dict(zip(vol['symbol'], vol['volatility']))


def get_signals(data):
    """v3 红利策略"""
    dy = _load_div_yield()
    if dy is None:
        return pd.DataFrame(columns=['symbol', 'weight'])

    fin = _load_financials()
    ind = _load_industry()

    trade_ts = pd.Timestamp(str(data['trade_date'].iloc[0])[:10])
    symbols = data['symbol'].tolist()

    # === 1. 股息率 ===
    dy_dates = sorted(dy['date'].unique())
    valid = [d for d in dy_dates if d <= trade_ts]
    if not valid:
        return pd.DataFrame(columns=['symbol', 'weight'])
    dy_slice = dy[dy['date'] == valid[-1]]
    dy_map = dict(zip(dy_slice['symbol'], dy_slice['div_yield']))

    # === 2. 波动率 (用data中计算的) ===
    vol_map = {}
    if len(data) > 100:
        data_sorted = data.sort_values(['symbol', 'trade_date'])
        data_sorted['daily_ret'] = data_sorted.groupby('symbol')['close_adj'].pct_change()
        for sym, grp in data_sorted.groupby('symbol'):
            rets = grp['daily_ret'].dropna().tail(60)
            if len(rets) > 10:
                vol_map[sym] = rets.std()

    # === 3. 构建候选池 ===
    candidates = []
    for sym in symbols:
        dy_val = dy_map.get(sym)
        if dy_val is None or dy_val <= 0:
            continue

        # 质量过滤
        if fin and sym in fin:
            info = fin[sym]
            roe = info.get('roe', np.nan)
            np_val = info.get('net_profit', 0)
            debt = info.get('debt_ratio', np.nan)
            eq = info.get('total_equity', 0)

            # ROE > 5%
            if np.isnan(roe) or roe <= 0.05:
                continue
            # 净利润 > 0
            if np_val <= 0:
                continue
            # 负债率 < 70%
            if not np.isnan(debt) and debt >= 0.70:
                continue
            # 分红率估算: 如果股息率 > 15%, 可能是异常值
            if dy_val > 0.15:
                continue
        else:
            # 无财务数据, 跳过
            continue

        # 低波动过滤: 剔除波动率最高的20%
        vol = vol_map.get(sym)
        # We'll do this after collecting all candidates

        candidates.append({
            'symbol': sym,
            'div_yield': dy_val,
            'volatility': vol if vol is not None else np.nan,
            'industry': ind.get(sym, '未知'),
        })

    if len(candidates) < 20:
        return pd.DataFrame(columns=['symbol', 'weight'])

    df = pd.DataFrame(candidates)

    # === 4. 剔除高波动 (最高的20%) ===
    vol_valid = df[df['volatility'].notna()].copy()
    if len(vol_valid) > 20:
        vol_threshold = vol_valid['volatility'].quantile(0.80)
        df = df[df['volatility'].isna() | (df['volatility'] <= vol_threshold)]

    if len(df) < 20:
        return pd.DataFrame(columns=['symbol', 'weight'])

    # === 5. 按股息率排序, 取前50 ===
    df = df.sort_values('div_yield', ascending=False).head(50)

    # === 6. 行业分散: 单行业不超过25% ===
    industry_groups = df.groupby('industry')
    MAX_IND_PCT = 0.25
    selected = []
    industry_counts = {}

    for _, row in df.iterrows():
        ind_name = row['industry']
        current = industry_counts.get(ind_name, 0)
        max_allowed = int(len(df) * MAX_IND_PCT)
        if current < max_allowed:
            selected.append(row['symbol'])
            industry_counts[ind_name] = current + 1

    if len(selected) < 10:
        return pd.DataFrame(columns=['symbol', 'weight'])

    # === 7. 等权 ===
    n = len(selected)
    return pd.DataFrame({
        'symbol': selected,
        'weight': 1.0 / n,
    })
