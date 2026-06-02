import numpy as np
import pandas as pd
from research_core.factor_engine.alphas101 import Alpha101Registry
from research_core.factor_engine.barra_factors import BarraFactorRegistry

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
print(f"Panel shape: {panel.shape}\n")

alpha_factors = Alpha101Registry.get_all_factors()
print(f"=== Testing {len(alpha_factors)} Alpha101 Factors ===\n")

success = 0
failed = []
for factor in alpha_factors:
    try:
        result = factor.compute(panel)
        n_valid = result.values.notna().sum()
        print(f"  OK  {factor.metadata.factor_id:20s} coverage={result.coverage:3d} valid={n_valid:3d}")
        success += 1
    except Exception as e:
        print(f"  FAIL {factor.metadata.factor_id:20s} error={str(e)[:60]}")
        failed.append((factor.metadata.factor_id, str(e)))

print(f"\nAlpha101 Results: {success}/{len(alpha_factors)} passed, {len(failed)} failed")
if failed:
    print("Failed factors:")
    for fid, err in failed:
        print(f"  {fid}: {err[:80]}")

barra_factors = BarraFactorRegistry.get_all_factors()
print(f"\n=== Testing {len(barra_factors)} Barra Factors ===\n")

b_success = 0
b_failed = []
for factor in barra_factors:
    try:
        if factor.metadata.factor_id == "barra_size":
            panel_with_mv = panel.copy()
            panel_with_mv["total_mv"] = panel_with_mv["close"] * panel_with_mv["volume"]
            result = factor.compute(panel_with_mv)
        elif factor.metadata.factor_id == "barra_value":
            panel_with_bp = panel.copy()
            panel_with_bp["total_mv"] = panel_with_bp["close"] * panel_with_bp["volume"]
            panel_with_bp["total_assets"] = panel_with_bp["total_mv"] * 2
            panel_with_bp["total_liab"] = panel_with_bp["total_mv"] * 0.5
            result = factor.compute(panel_with_bp)
        elif factor.metadata.factor_id == "barra_earnings_yield":
            panel_with_ep = panel.copy()
            panel_with_ep["net_profit"] = panel_with_ep["close"] * panel_with_ep["volume"] * 0.05
            panel_with_ep["total_mv"] = panel_with_ep["close"] * panel_with_ep["volume"]
            result = factor.compute(panel_with_ep)
        elif factor.metadata.factor_id == "barra_beta":
            panel_with_idx = panel.copy()
            panel_with_idx["index_close"] = panel_with_idx.groupby("date")["close"].transform("mean")
            result = factor.compute(panel_with_idx)
        else:
            result = factor.compute(panel)
        n_valid = result.values.notna().sum()
        print(f"  OK  {factor.metadata.factor_id:20s} coverage={result.coverage:3d} valid={n_valid:3d}")
        b_success += 1
    except Exception as e:
        print(f"  FAIL {factor.metadata.factor_id:20s} error={str(e)[:60]}")
        b_failed.append((factor.metadata.factor_id, str(e)))

print(f"\nBarra Results: {b_success}/{len(barra_factors)} passed, {len(b_failed)} failed")
print(f"\n=== Total: {success + b_success}/{len(alpha_factors) + len(barra_factors)} factors working ===")
