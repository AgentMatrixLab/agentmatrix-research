from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from common.paths import data_path
from research_core.factor_engine.data_provider import MarketDataProvider
from research_core.factor_engine.alphas101 import Alpha101Registry
from research_core.factor_engine.barra_factors import BarraFactorRegistry
from research_core.factor_engine.evaluator import FactorEvaluator
from research_core.factor_engine.batch_evaluator import BatchFactorEvaluator
from research_core.factor_engine.ai_miner import AIFactorMiner


def run_single_factor(args):
    print(f"=== Single Factor Evaluation: {args.factor_id} ===\n")

    provider = MarketDataProvider()
    print("[1/4] Fetching stock list...")
    stock_list = provider.get_stock_list()
    symbols = stock_list["symbol"].head(args.n_stocks).tolist()
    print(f"  Using {len(symbols)} stocks")

    print("[2/4] Fetching historical data...")
    panel = provider.build_panel(symbols, start_date=args.start_date, end_date=args.end_date)
    if panel.empty:
        print("ERROR: No data fetched. Check network or reduce n_stocks.")
        return
    print(f"  Panel shape: {panel.shape}")

    print("[3/4] Computing factor...")
    factor = None
    for registry in [Alpha101Registry, BarraFactorRegistry]:
        factor = registry.get_factor(args.factor_id)
        if factor is not None:
            break
    if factor is None:
        print(f"ERROR: Factor '{args.factor_id}' not found in any registry.")
        print(f"  Available Alpha101: {Alpha101Registry.list_factors()}")
        print(f"  Available Barra: {BarraFactorRegistry.list_factors()}")
        return

    result = factor.compute(panel)
    print(f"  Factor computed: coverage={result.coverage}, ratio={result.coverage_ratio:.2%}")
    print(f"  Top 5 values:\n{result.values.nlargest(5)}")

    print("[4/4] Evaluating factor...")
    close_matrix = provider.build_close_matrix(symbols, args.start_date, args.end_date)
    evaluator = FactorEvaluator()
    eval_result = evaluator.full_evaluation(
        factor_values=_pivot_factor(panel, result),
        close_matrix=close_matrix,
        factor_id=args.factor_id,
    )
    print(f"\n  IC Analysis: {json.dumps(eval_result.get('ic_analysis', {}), indent=2)}")
    print(f"  Layer Backtest: {json.dumps(eval_result.get('layer_backtest', {}), indent=2)}")
    print(f"  Turnover: {json.dumps(eval_result.get('turnover', {}), indent=2)}")


def run_batch_eval(args):
    print("=== Batch Factor Evaluation ===\n")

    provider = MarketDataProvider()
    print("[1/4] Fetching stock list...")
    stock_list = provider.get_stock_list()
    symbols = stock_list["symbol"].head(args.n_stocks).tolist()
    print(f"  Using {len(symbols)} stocks")

    print("[2/4] Fetching historical data...")
    panel = provider.build_panel(symbols, start_date=args.start_date, end_date=args.end_date)
    if panel.empty:
        print("ERROR: No data fetched.")
        return
    close_matrix = provider.build_close_matrix(symbols, args.start_date, args.end_date)
    print(f"  Panel shape: {panel.shape}, Close matrix shape: {close_matrix.shape}")

    print("[3/4] Collecting factors...")
    factors = []
    if args.include_alpha101:
        factors.extend(Alpha101Registry.get_all_factors())
    if args.include_barra:
        factors.extend(BarraFactorRegistry.get_all_factors())
    print(f"  Total factors to evaluate: {len(factors)}")

    print("[4/4] Running batch evaluation...")
    batch_eval = BatchFactorEvaluator(close_matrix)
    results_df = batch_eval.evaluate_batch(factors, panel)

    print("\n=== Results Summary ===")
    print(results_df[["factor_id", "name", "category", "ic_1d_mean", "ir_1d", "status"]].to_string())

    summary = batch_eval.generate_summary(results_df)
    print(f"\nSummary: {json.dumps(summary, indent=2, default=str)}")

    output_path = batch_eval.save_results(results_df)
    print(f"\nResults saved to: {output_path}")


def run_ai_mine(args):
    print("=== AI Factor Mining ===\n")

    provider = MarketDataProvider()
    print("[1/3] Fetching data...")
    stock_list = provider.get_stock_list()
    symbols = stock_list["symbol"].head(args.n_stocks).tolist()
    panel = provider.build_panel(symbols, start_date=args.start_date, end_date=args.end_date)
    close_matrix = provider.build_close_matrix(symbols, args.start_date, args.end_date)
    if panel.empty:
        print("ERROR: No data fetched.")
        return
    print(f"  Panel shape: {panel.shape}")

    print("[2/3] Initializing AI Factor Miner...")
    miner = AIFactorMiner(
        close_matrix=close_matrix,
        panel_data=panel,
        ic_threshold=args.ic_threshold,
        ir_threshold=args.ir_threshold,
    )

    print(f"[3/3] Mining {args.n_candidates} candidate factors...")
    mined = miner.mine(n_candidates=args.n_candidates)

    print(f"\n=== Mining Results ===")
    print(f"Total valid factors found: {len(mined)}")

    top = miner.get_top_factors(top_n=10)
    for i, f in enumerate(top):
        print(f"  {i+1}. IC={f.ic_1d:.4f} IR={f.ir_1d:.4f} | {f.expression[:70]}")

    output_path = miner.save_results()
    print(f"\nResults saved to: {output_path}")


def _pivot_factor(panel: pd.DataFrame, result) -> pd.DataFrame:
    if "date" not in panel.columns or "symbol" not in panel.columns:
        return pd.DataFrame()
    pivot = panel.pivot_table(index="date", columns="symbol", values="close")
    matrix = pivot.copy()
    matrix.iloc[:] = np.nan
    for symbol, val in result.values.items():
        if symbol in matrix.columns:
            matrix.iloc[-1][symbol] = val
    return matrix


def list_factors(args):
    print("Available Factors:\n")
    print("=== WorldQuant Alpha 101 ===")
    for fid in Alpha101Registry.list_factors():
        f = Alpha101Registry.get_factor(fid)
        print(f"  {fid}: {f.metadata.name} - {f.metadata.description[:60]}")

    print("\n=== Barra Style Factors ===")
    for fid in BarraFactorRegistry.list_factors():
        f = BarraFactorRegistry.get_factor(fid)
        print(f"  {fid}: {f.metadata.name} - {f.metadata.description[:60]}")


def main():
    parser = argparse.ArgumentParser(description="Factor Engine CLI")
    subparsers = parser.add_subparsers(dest="command")

    list_parser = subparsers.add_parser("list", help="List available factors")
    list_parser.set_defaults(func=list_factors)

    single_parser = subparsers.add_parser("eval", help="Evaluate a single factor")
    single_parser.add_argument("--factor-id", required=True, help="Factor ID to evaluate")
    single_parser.add_argument("--n-stocks", type=int, default=50)
    single_parser.add_argument("--start-date", default="20230101")
    single_parser.add_argument("--end-date", default=None)
    single_parser.set_defaults(func=run_single_factor)

    batch_parser = subparsers.add_parser("batch", help="Batch evaluate all factors")
    batch_parser.add_argument("--n-stocks", type=int, default=50)
    batch_parser.add_argument("--start-date", default="20230101")
    batch_parser.add_argument("--end-date", default=None)
    batch_parser.add_argument("--include-alpha101", action="store_true", default=True)
    batch_parser.add_argument("--include-barra", action="store_true", default=True)
    batch_parser.set_defaults(func=run_batch_eval)

    mine_parser = subparsers.add_parser("mine", help="AI factor mining")
    mine_parser.add_argument("--n-stocks", type=int, default=50)
    mine_parser.add_argument("--start-date", default="20230101")
    mine_parser.add_argument("--end-date", default=None)
    mine_parser.add_argument("--n-candidates", type=int, default=50)
    mine_parser.add_argument("--ic-threshold", type=float, default=0.03)
    mine_parser.add_argument("--ir-threshold", type=float, default=0.3)
    mine_parser.set_defaults(func=run_ai_mine)

    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        return

    import numpy as np
    args.func(args)


if __name__ == "__main__":
    main()
