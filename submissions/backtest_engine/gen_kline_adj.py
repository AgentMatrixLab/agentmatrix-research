"""
生成 kline_adj.parquet: 逐年K线合并 + 复权因子复权
"""
import os, glob, time, gc
import pandas as pd
import numpy as np

DATA = "E:/custom_engine/data"
KL_DIR = os.path.join(DATA, "kline")
OUT = os.path.join(DATA, "kline_adj.parquet")

print("=" * 60)
print("生成 kline_adj.parquet")
print("=" * 60)

# === 1. 加载复权因子 ===
print("[1] 加载复权因子...", end=' ', flush=True)
t0 = time.time()
adj = pd.read_parquet(os.path.join(DATA, "ex_factor_full.parquet"))
print(f"{len(adj):,}行, cols={list(adj.columns)}, {time.time()-t0:.1f}s")

# 统一列名
if 'symbol' not in adj.columns and 'order_book_id' in adj.columns:
    adj = adj.rename(columns={'order_book_id': 'symbol'})

# 确定日期列
date_col = None
for dc in ['announcement_date', 'date', 'trade_date']:
    if dc in adj.columns:
        date_col = dc
        break

if date_col is None:
    raise ValueError(f"找不到日期列: {list(adj.columns)}")

adj[date_col] = pd.to_datetime(adj[date_col])

# 股票代码格式统一
sample = str(adj['symbol'].iloc[0])
print(f"  复权因子股票格式: {sample}")
print(f"  日期列: {date_col}")
print(f"  日期范围: {adj[date_col].min().date()} ~ {adj[date_col].max().date()}")

# === 2. 加载逐年K线 ===
print("\n[2] 加载逐年K线...")
kline_files = sorted(glob.glob(os.path.join(KL_DIR, "kline_20*.parquet")))
print(f"  {len(kline_files)} 个文件")

all_parts = []
for f in kline_files:
    bn = os.path.basename(f)
    t0 = time.time()
    df = pd.read_parquet(f)
    
    # 统一列名
    for old, new in [('order_book_id', 'symbol'), ('date', 'trade_date')]:
        if old in df.columns and new not in df.columns:
            df = df.rename(columns={old: new})
    
    # 确保有 trade_date
    if 'trade_date' not in df.columns:
        print(f"  SKIP {bn}: 无日期列")
        continue
    
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    
    # 统一symbol格式
    df['symbol'] = df['symbol'].astype(str)
    
    # 确保有amount列 (total_turnover → amount)
    if 'amount' not in df.columns and 'total_turnover' in df.columns:
        df = df.rename(columns={'total_turnover': 'amount'})
    
    dmin, dmax = df['trade_date'].min().date(), df['trade_date'].max().date()
    n_sym = df['symbol'].nunique()
    print(f"  {bn}: {len(df):,}行, {n_sym}只, {dmin}~{dmax}, {time.time()-t0:.1f}s")
    all_parts.append(df)

print(f"\n  合并中...", end=' ', flush=True)
t0 = time.time()
kline = pd.concat(all_parts, ignore_index=True)
del all_parts; gc.collect()
print(f"{time.time()-t0:.1f}s")
print(f"  合并后: {len(kline):,}行, {kline['symbol'].nunique()}只")
print(f"  日期: {kline['trade_date'].min().date()} ~ {kline['trade_date'].max().date()}")

# === 3. 合并复权因子 (forward fill) ===
print("\n[3] 合并复权因子...", end=' ', flush=True)
t0 = time.time()

# 统一symbol格式
adj['symbol'] = adj['symbol'].astype(str)

# 按symbol+date排序后forward fill
adj_sorted = adj.sort_values(['symbol', date_col])
adj_sorted = adj_sorted.rename(columns={date_col: 'trade_date'})

# 只保留需要的列
adj_cols = ['symbol', 'trade_date']
for ac in ['ex_factor', 'ex_cum_factor', 'cum_factor']:
    if ac in adj_sorted.columns:
        adj_cols.append(ac)

adj_light = adj_sorted[adj_cols].copy()

# Merge (left join on symbol+trade_date)
kline = kline.merge(adj_light, on=['symbol', 'trade_date'], how='left')

# Forward fill ex_factor per symbol
for ac in ['ex_factor', 'ex_cum_factor', 'cum_factor']:
    if ac in kline.columns:
        kline[ac] = kline.groupby('symbol')[ac].ffill()
        kline[ac] = kline[ac].fillna(1.0)

# 用cum_factor做后复权
if 'cum_factor' in kline.columns:
    factor_col = 'cum_factor'
elif 'ex_cum_factor' in kline.columns:
    factor_col = 'ex_cum_factor'
elif 'ex_factor' in kline.columns:
    factor_col = 'ex_factor'
else:
    factor_col = None

if factor_col:
    print(f"\n  复权因子列: {factor_col}")
    for col in ['open', 'high', 'low', 'close']:
        if col in kline.columns:
            kline[f'{col}_adj'] = kline[col] * kline[factor_col]
    print(f"  已生成: open_adj, high_adj, low_adj, close_adj")
else:
    print("  ⚠️ 无复权因子列，直接使用原始价格")
    for col in ['open', 'high', 'low', 'close']:
        if col in kline.columns:
            kline[f'{col}_adj'] = kline[col]

print(f"  耗时: {time.time()-t0:.1f}s")

# 计算 ret_1d
print("\n[4] 计算 ret_1d...", end=' ', flush=True)
t0 = time.time()
kline = kline.sort_values(['symbol', 'trade_date'])
kline['ret_1d'] = kline.groupby('symbol')['close_adj'].pct_change()
print(f"{time.time()-t0:.1f}s")

# === 4. 保存 ===
print(f"\n[5] 保存...", end=' ', flush=True)
t0 = time.time()
kline.to_parquet(OUT, index=False, compression='snappy')
sz = os.path.getsize(OUT) / 1024 / 1024
print(f"{time.time()-t0:.1f}s")

print(f"\n  {OUT} ({sz:.1f}MB)")
print(f"  行: {len(kline):,}")
print(f"  列: {list(kline.columns)}")
print(f"  股票: {kline['symbol'].nunique()}")
print(f"  日期: {kline['trade_date'].min().date()} ~ {kline['trade_date'].max().date()}")
print("\n=== 完成 ===")
