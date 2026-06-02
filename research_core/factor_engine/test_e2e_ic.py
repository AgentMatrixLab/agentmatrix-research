import numpy as np
import pandas as pd
from research_core.factor_engine.alphas101 import Alpha101Registry
from research_core.factor_engine.barra_factors import BarraFactorRegistry, VolatilityFactor, MomentumFactor, LiquidityFactor
from research_core.factor_engine.evaluator import FactorEvaluator

np.random.seed(42)
n_days = 250
n_stocks = 50
dates = pd.date_range("2024-01-01", periods=n_days, freq="B")
symbols = [f"STK{i:03d}" for i in range(n_stocks)]

rows = []
for sym in symbols:
    close = 100.0
    for d in dates:
        ret = np.random.normal(0.0005, 0.025)
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
print(f"Date range: {panel['date'].min().date()} ~ {panel['date'].max().date()}")
print(f"Stocks: {n_stocks}, Days: {n_days}")

close_matrix = panel.pivot_table(index="date", columns="symbol", values="close")
print(f"Close matrix shape: {close_matrix.shape}")

evaluator = FactorEvaluator()
forward_rets = evaluator.compute_forward_returns(close_matrix, [1, 5, 20])
print(f"Forward returns computed for periods: {list(forward_rets.keys())}")

test_factors = [
    Alpha101Registry.get_factor("alpha101_012"),
    Alpha101Registry.get_factor("alpha101_033"),
    Alpha101Registry.get_factor("alpha101_010"),
    Alpha101Registry.get_factor("alpha101_041"),
    Alpha101Registry.get_factor("alpha101_053"),
    VolatilityFactor(lookback=20),
    MomentumFactor(lookback=60, skip_days=10),
    LiquidityFactor(lookback=20),
]

print(f"\n{'='*80}")
print(f"{'Factor IC Evaluation Report':^80}")
print(f"{'='*80}")

all_ic_results = []
for factor in test_factors:
    fid = factor.metadata.factor_id
    try:
        result = factor.compute(panel)
        n_valid = result.values.notna().sum()
        if n_valid < 5:
            print(f"  SKIP {fid}: only {n_valid} valid values")
            continue

        factor_matrix = close_matrix.copy()
        factor_matrix.iloc[:] = np.nan

        for date in panel["date"].unique():
            date_data = panel[panel["date"] == date]
            try:
                date_result = factor.compute(panel[panel["date"] <= date])
                for sym in date_result.values.index:
                    if sym in factor_matrix.columns and date in factor_matrix.index:
                        factor_matrix.loc[date, sym] = date_result.values.get(sym, np.nan)
            except Exception:
                pass

        ic_metrics = evaluator.compute_ic_metrics(
            factor_matrix, forward_rets[1], fid, "1d"
        )
        ic_5d = evaluator.compute_ic_metrics(
            factor_matrix, forward_rets[5], fid, "5d"
        )

        all_ic_results.append({
            "factor_id": fid,
            "name": factor.metadata.name,
            "ic_1d_mean": ic_metrics.ic_mean,
            "ic_1d_std": ic_metrics.ic_std,
            "ir_1d": ic_metrics.ir,
            "ic_1d_pos": ic_metrics.ic_positive_ratio,
            "ic_5d_mean": ic_5d.ic_mean,
            "ir_5d": ic_5d.ir,
            "valid": n_valid,
        })
        print(f"  OK  {fid:<22s} IC(1d)={ic_metrics.ic_mean:+.4f} IR={ic_metrics.ir:+.4f} IC>0={ic_metrics.ic_positive_ratio:.1%}  |  IC(5d)={ic_5d.ic_mean:+.4f} IR={ic_5d.ir:+.4f}")
    except Exception as e:
        print(f"  FAIL {fid}: {str(e)[:50]}")

if all_ic_results:
    ic_df = pd.DataFrame(all_ic_results)
    ic_df = ic_df.sort_values("ir_1d", ascending=False, key=abs, na_position="last")

    print(f"\n{'='*80}")
    print(f"{'Summary (sorted by |IR|)':^80}")
    print(f"{'='*80}")
    print(f"{'Factor':<22s} {'IC(1d)':>8s} {'IR(1d)':>8s} {'IC>0%':>7s} {'IC(5d)':>8s} {'IR(5d)':>8s}")
    print(f"{'-'*80}")
    for _, row in ic_df.iterrows():
        print(f"{row['factor_id']:<22s} {row['ic_1d_mean']:>+8.4f} {row['ir_1d']:>+8.4f} {row['ic_1d_pos']:>6.1%} {row['ic_5d_mean']:>+8.4f} {row['ir_5d']:>+8.4f}")

    print(f"\n{'='*80}")
    print(f"Layer Backtest for Top Factor")
    print(f"{'='*80}")
    top_factor = test_factors[0]
    top_result = top_factor.compute(panel)
    factor_matrix = close_matrix.copy()
    factor_matrix.iloc[:] = np.nan
    for date in panel["date"].unique():
        try:
            date_result = top_factor.compute(panel[panel["date"] <= date])
            for sym in date_result.values.index:
                if sym in factor_matrix.columns and date in factor_matrix.index:
                    factor_matrix.loc[date, sym] = date_result.values.get(sym, np.nan)
        except Exception:
            pass

    layer_result = evaluator.layer_backtest(factor_matrix, close_matrix, n_layers=5)
    if layer_result:
        print(f"\nLayer backtest for {top_factor.metadata.factor_id}:")
        if hasattr(layer_result, "layer_returns"):
            for layer_name, ret in layer_result.layer_returns.items():
                print(f"  {layer_name}: mean return = {ret:.4f}")
        elif isinstance(layer_result, dict):
            for layer, ret in layer_result.items():
                print(f"  {layer}: mean return = {ret:.4f}")
        else:
            print(f"  Result: {layer_result}")

print("\n=== End-to-end test complete! ===")
