"""回测: 小市值(月) - 输出全部写文件避免截断"""
import sys, os, time, traceback, gc
sys.path.insert(0, os.path.dirname(__file__))

LOG = os.path.join(os.path.dirname(__file__), '_log.txt')
def log(msg):
    print(msg)
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(msg + '\n')

with open(LOG, 'w') as f: f.write('')

log("=" * 55)
log("  小市值(月) 回测")
log("=" * 55)

# ⚠️ 先导入策略模块 (在大量数据加载前，避免OOM)
log("\n[1/4] 加载策略...")
from strategies import discover_strategies
strategies = discover_strategies()
strat = strategies.get("小市值(月)")
if strat is None:
    log("  ERROR: 策略未找到")
    sys.exit(1)
log(f"  策略: {strat.__name__ if hasattr(strat, '__name__') else str(strat)}")

# 2. 加载数据 (此时策略已导入)
log("\n[2/4] 加载K线...")
from engine.data_manager import load_kline
t0 = time.time()
kline = load_kline()
et = time.time() - t0
log(f"  完成: {len(kline):,}r {et:.1f}s")
log(f"  日期: {kline['trade_date'].min().date()} ~ {kline['trade_date'].max().date()}")
log(f"  股票: {kline['symbol'].nunique()}")
gc.collect()

# 3. 回测
log("\n[3/4] 回测引擎...")
from engine.backtest import BacktestEngine
from engine.metrics import format_report

engine = BacktestEngine(skip_load=True)
engine.kline = kline
engine.kline['close_adj'] = engine.kline['close']
engine.kline['open_adj'] = engine.kline['open']
engine.kline['high_adj'] = engine.kline['high']
engine.kline['low_adj'] = engine.kline['low']
engine.calendar = kline[['trade_date']].drop_duplicates().sort_values('trade_date').reset_index(drop=True)
engine.status = None
engine._valid_symbols = None
engine.adj = None
engine.financial = None

log(f"  就绪, 开始回测...")
t0 = time.time()
try:
    nav_df, metrics = engine.run_all({"小市值(月)": strat}, rebalance_freq=20)
except Exception as e:
    log(f"  ERROR: {e}")
    log(traceback.format_exc())
    sys.exit(1)
et = time.time() - t0
log(f"  耗时: {et:.1f}s")

# 4. 输出
log(f"\n[4/4] 保存结果...")
from config import OUTPUT_DIR
os.makedirs(OUTPUT_DIR, exist_ok=True)

report = format_report(metrics)
log(report)

with open(os.path.join(OUTPUT_DIR, "report.txt"), 'w', encoding='utf-8') as f:
    f.write(report)

nav_path = os.path.join(OUTPUT_DIR, "small_cap_nav.csv")
if isinstance(nav_df, dict):
    for name, df in nav_df.items():
        df.to_csv(nav_path)
else:
    nav_df.to_csv(nav_path)

log(f"\n✅ Done! {OUTPUT_DIR}")
log(f"   {nav_path}")
