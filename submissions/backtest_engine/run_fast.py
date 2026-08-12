"""快速回测 — 红利v6 2010-2026 (PyArrow零拷贝)"""
import sys, os, time, gc
sys.path.insert(0, os.path.dirname(__file__))
os.chdir(os.path.dirname(__file__))

import importlib, pandas as pd, numpy as np
from config import DATA_DIR
from engine.backtest import BacktestEngine

mod = importlib.import_module("strategies.dividend_yield_v6")
fn = mod.get_signals
print("策略: 红利v6(修复后)", flush=True)

FULL_PATH = os.path.join(DATA_DIR, "kline_full.parquet")
print(f"加载: {FULL_PATH}", flush=True)

t0 = time.time()
# PyArrow零拷贝读取 + 转为numpy类型以兼容pandas
import pyarrow.parquet as pq
table = pq.read_table(FULL_PATH)
# 字符串替换在Arrow层做
import pyarrow.compute as pc
sym = pc.replace_substring(table.column('symbol'), '.XSHE', '.SZ')
sym = pc.replace_substring(sym, '.XSHG', '.SH')
table = table.set_column(0, 'symbol', sym)
# 只保留必要列
table = table.select(['symbol', 'trade_date', 'close', 'volume'])
# 转为pandas (此时内存峰值较低)
k = table.to_pandas()
del table; gc.collect()
# 转换类型
k['symbol'] = k['symbol'].astype('category')
# trade_date保留为numpy datetime64
print(f"K线: {len(k):,}r {time.time()-t0:.1f}s ({k['trade_date'].min().date()}~{k['trade_date'].max().date()})", flush=True)
print(f"内存: {k.memory_usage(deep=True).sum()/1024/1024:.0f}MB", flush=True)
gc.collect()

engine = BacktestEngine(skip_load=True)
engine.kline = k
engine.kline['close_adj'] = engine.kline['close']
engine.kline['open_adj'] = engine.kline['close']
engine.kline['high_adj'] = engine.kline['close']
engine.kline['low_adj'] = engine.kline['close']
engine.calendar = k[['trade_date']].drop_duplicates().sort_values('trade_date').reset_index(drop=True)
engine.status = None; engine._valid_symbols = None; engine.adj = None; engine.financial = None

print("开始回测...", flush=True)
t0 = time.time()
nav_df, metrics, report = engine.run_all(
    {"红利v6(修复后)": fn}, rebalance_freq=126,
    start_date="2010-01-04", end_date="2026-07-08")
print(f"回测耗时: {time.time()-t0:.0f}s", flush=True)
print(report, flush=True)

# 保存净值
from config import OUTPUT_DIR
os.makedirs(OUTPUT_DIR, exist_ok=True)
nav_path = os.path.join(OUTPUT_DIR, "dividend_v6_2010_2026_nav.csv")
if isinstance(nav_df, dict):
    for name, df in nav_df.items():
        df.to_csv(nav_path, index=False)
else:
    nav_df.to_csv(nav_path, index=False)
print(f"净值保存: {nav_path}")

# 生成可视化
from generate_report import generate_html
out = generate_html(OUTPUT_DIR)
if out:
    print(f"可视化面板: file://{os.path.abspath(out)}")
print("=== 完成 ===")
