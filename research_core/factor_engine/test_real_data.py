import sys
import numpy as np
import pandas as pd
from research_core.factor_engine.data_provider import MarketDataProvider
from research_core.factor_engine.alphas101 import Alpha101Registry
from research_core.factor_engine.barra_factors import BarraFactorRegistry
from research_core.factor_engine.evaluator import FactorEvaluator

provider = MarketDataProvider()

print("[1/5] Fetching stock list...")
stock_list = provider.get_stock_list()
if stock_list.empty:
    print("ERROR: Could not fetch stock list. Check network.")
    sys.exit(1)
print(f"  Total stocks: {len(stock_list)}")

n_stocks = 20
symbols = stock_list["symbol"].head(n_stocks).tolist()
print(f"  Using first {n_stocks} stocks: {symbols[:5]}...")

print("\n[2/5] Fetching historical data (this may take a while)...")
panel = provider.build_panel(symbols, start_date="20240101", end_date="20250531")
if panel.empty:
    print("ERROR: No data fetched.")
    sys.exit(1)
print(f"  Panel shape: {panel.shape}")
print(f"  Date range: {panel['date'].min()} ~ {panel['date'].max()}")
print(f"  Columns: {list(panel.columns)}")

print("\n[3/5] Computing factors...")
alpha_factors = Alpha101Registry.get_all_factors()
barra_factors = BarraFactorRegistry.get_all_factors()
all_factors = alpha_factors + barra_factors

factor_results = {}
for factor in all_factors:
    fid = factor.metadata.factor_id
    try:
        if fid == "barra_size":
            panel_mv = panel.copy()
            panel_mv["total_mv"] = panel_mv["close"] * panel_mv["volume"]
            result = factor.compute(panel_mv)
        elif fid == "barra_value":
            panel_v = panel.copy()
            panel_v["total_mv"] = panel_v["close"] * panel_v["volume"]
            panel_v["total_assets"] = panel_v["total_mv"] * 2
            panel_v["total_liab"] = panel_v["total_mv"] * 0.5
            result = factor.compute(panel_v)
        elif fid == "barra_earnings_yield":
            panel_e = panel.copy()
            panel_e["net_profit"] = panel_e["close"] * panel_e["volume"] * 0.05
            panel_e["total_mv"] = panel_e["close"] * panel_e["volume"]
            result = factor.compute(panel_e)
        elif fid == "barra_beta":
            panel_b = panel.copy()
            panel_b["index_close"] = panel_b.groupby("date")["close"].transform("mean")
            result = factor.compute(panel_b)
        else:
            result = factor.compute(panel)
        n_valid = result.values.notna().sum()
        factor_results[fid] = result
        print(f"  OK  {fid:20s} valid={n_valid:3d}")
    except Exception as e:
        print(f"  FAIL {fid:20s} {str(e)[:50]}")

print(f"\n  Successfully computed {len(factor_results)}/{len(all_factors)} factors")

print("\n[4/5] Building close matrix for IC evaluation...")
close_matrix = provider.build_close_matrix(symbols, "20240101", "20250531")
if close_matrix.empty:
    print("ERROR: Could not build close matrix.")
    sys.exit(1)
print(f"  Close matrix shape: {close_matrix.shape}")

print("\n[5/5] Running IC evaluation for top factors...")
evaluator = FactorEvaluator()
forward_rets = evaluator.compute_forward_returns(close_matrix, [1, 5, 20])
print(f"  Forward return periods: {list(forward_rets.keys())}")

ic_results = []
for fid, result in factor_results.items():
    if result.values.notna().sum() < 3:
        continue
    factor_matrix = close_matrix.copy()
    factor_matrix.iloc[:] = np.nan
    latest_date = panel["date"].max()
    for sym in result.values.index:
        if sym in factor_matrix.columns:
            factor_matrix.loc[factor_matrix.index[-1], sym] = result.values.get(sym, np.nan)

    try:
        ic_metrics = evaluator.compute_ic_metrics(
            factor_matrix, forward_rets[1], fid, "1d"
        )
        ic_results.append({
            "factor_id": fid,
            "ic_mean": ic_metrics.ic_mean,
            "ic_std": ic_metrics.ic_std,
            "ir": ic_metrics.ir,
            "ic_positive_ratio": ic_metrics.ic_positive_ratio,
            "ic_t_stat": ic_metrics.ic_t_stat,
        })
    except Exception as e:
        print(f"  IC eval failed for {fid}: {str(e)[:40]}")

if ic_results:
    ic_df = pd.DataFrame(ic_results)
    ic_df = ic_df.sort_values("ic_mean", ascending=False, key=abs, na_position="last")
    print(f"\n{'='*70}")
    print(f"{'Factor IC Summary':^70}")
    print(f"{'='*70}")
    print(f"{'Factor ID':<22s} {'IC Mean':>8s} {'IC Std':>8s} {'IR':>8s} {'IC>0%':>8s} {'t-stat':>8s}")
    print(f"{'-'*70}")
    for _, row in ic_df.iterrows():
        print(f"{row['factor_id']:<22s} {row['ic_mean']:>8.4f} {row['ic_std']:>8.4f} {row['ir']:>8.4f} {row['ic_positive_ratio']:>7.1%} {row['ic_t_stat']:>8.2f}")
    print(f"{'='*70}")
    print(f"\nTop 5 by |IC mean|:")
    for _, row in ic_df.head(5).iterrows():
        direction = "正向" if row["ic_mean"] > 0 else "反向"
        print(f"  {row['factor_id']}: IC={row['ic_mean']:.4f} IR={row['ir']:.4f} ({direction})")
else:
    print("\nNo IC results computed (insufficient data for cross-sectional IC).")
    print("Note: IC requires multiple dates with cross-sectional factor values.")
    print("Current implementation uses only the latest date's factor values.")
    print("For proper IC analysis, factor values need to be computed for each date.")

print("\nDone!")
