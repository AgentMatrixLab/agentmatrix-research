"""跑单个策略回测 + 输出结果"""
import sys, os, time
sys.path.insert(0, os.path.dirname(__file__))

from engine.backtest import BacktestEngine
from config import OUTPUT_DIR
from engine.data_manager import load_kline

STRATEGY = "小市值(月)"
WINDOW_YEARS = 5

print(f"策略: {STRATEGY}")

# 1. 加载数据
t0 = time.time()
kline = load_kline()
if kline is None:
    print("❌ K线数据加载失败")
    sys.exit(1)
print(f"K线: {len(kline):,}行, {kline['symbol'].nunique()}只, "
      f"{kline['trade_date'].min().date()}~{kline['trade_date'].max().date()}, "
      f"{time.time()-t0:.1f}s")

# 2. 回测引擎
engine = BacktestEngine(data_dir=os.path.join(os.path.dirname(__file__), "data"))
engine.kline = kline
# 从K线提取日历
engine.calendar = kline[['trade_date']].drop_duplicates().sort_values('trade_date').reset_index(drop=True)
engine.status = None

# 3. 跑策略
from strategies import load_strategy
StrategyClass = load_strategy(STRATEGY)
strat = StrategyClass()

print(f"\n回测窗口: {WINDOW_YEARS}年, 初始资金: 1,000,000")
t1 = time.time()
result = engine.run(strat, window_years=WINDOW_YEARS)
print(f"回测耗时: {time.time()-t1:.1f}s")

# 4. 输出指标
print(f"\n{'='*50}")
print(f"策略: {STRATEGY}")
metrics = result.get('metrics', {}).get('total', {})
for k, v in metrics.items():
    if isinstance(v, float):
        print(f"  {k}: {v:.4f}")
    else:
        print(f"  {k}: {v}")
print(f"{'='*50}")

# 5. 输出trade log
trades = result.get('trades')
if trades is not None and len(trades) > 0:
    print(f"\n交易记录: {len(trades)} 条")
    print(trades.tail(10).to_string())
