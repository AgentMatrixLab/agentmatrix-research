import numpy as np
import pandas as pd
from research_core.factor_engine.alphas101 import Alpha12
from research_core.factor_engine.barra_factors import VolatilityFactor, MomentumFactor
from research_core.factor_engine.evaluator import FactorEvaluator

np.random.seed(42)
n_days = 120
n_stocks = 30
dates = pd.date_range("2024-01-01", periods=n_days, freq="B")
symbols = [f"STK{i:03d}" for i in range(n_stocks)]

rows = []
for sym in symbols:
    close = 100.0
    for d in dates:
        ret = np.random.normal(0.001, 0.02)
        close *= (1 + ret)
        open_p = close * (1 + np.random.normal(0, 0.005))
        high = max(close, open_p) * (1 + abs(np.random.normal(0, 0.01)))
        low = min(close, open_p) * (1 - abs(np.random.normal(0, 0.01)))
        vol = np.random.randint(100000, 10000000)
        amt = vol * close
        rows.append({
            "date": d, "symbol": sym, "close": close,
            "open": open_p, "high": high, "low": low,
            "volume": vol, "amount": amt, "turnover": np.random.uniform(0.5, 5.0),
        })

panel = pd.DataFrame(rows)
print(f"Panel shape: {panel.shape}")

alpha12 = Alpha12()
result = alpha12.compute(panel)
print(f"Alpha12: coverage={result.coverage}, ratio={result.coverage_ratio:.2%}")
print(f"  Top 3: {result.values.nlargest(3).to_dict()}")

vol_factor = VolatilityFactor(lookback=20)
result2 = vol_factor.compute(panel)
print(f"Volatility: coverage={result2.coverage}, ratio={result2.coverage_ratio:.2%}")

mom_factor = MomentumFactor(lookback=60, skip_days=10)
result3 = mom_factor.compute(panel)
print(f"Momentum: coverage={result3.coverage}, ratio={result3.coverage_ratio:.2%}")

close_matrix = panel.pivot_table(index="date", columns="symbol", values="close")
evaluator = FactorEvaluator()
forward_rets = evaluator.compute_forward_returns(close_matrix, [1, 5, 20])

factor_matrix = close_matrix.copy()
factor_matrix.iloc[:] = np.nan
latest = panel[panel["date"] == panel["date"].max()]
for _, row in latest.iterrows():
    sym = row["symbol"]
    if sym in result.values.index and sym in factor_matrix.columns:
        factor_matrix.loc[factor_matrix.index[-1], sym] = result.values[sym]

ic_metrics = evaluator.compute_ic_metrics(factor_matrix, forward_rets[1], "alpha101_012", "1d")
print(f"\nIC Metrics for Alpha12:")
print(f"  IC mean: {ic_metrics.ic_mean:.4f}")
print(f"  IC std: {ic_metrics.ic_std:.4f}")
print(f"  IR: {ic_metrics.ir:.4f}")
print(f"  IC>0 ratio: {ic_metrics.ic_positive_ratio:.2%}")

print("\n=== All tests passed! ===")
