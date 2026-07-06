"""
Export JQ truth CSV for AgentMatrix jq_gm proof-batch.

Run this INSIDE the GM terminal environment where:
  - gm_factor_lib.py is importable (GM SDK available)
  - JQ comparison data is available (v78 comparison CSV or JQ API access)

=== What this script does ===

1. Loads the 31 verified jq_gm factors (GM vs JQ 100% match at v78).
2. Generates a truth CSV in the wide format expected by factor_lab:
      date, code, factor_1, factor_2, ..., factor_N
3. Saves it to data/factor_lab/jq_gm_truth.csv (AgentMatrix workspace).
4. (Optional) Runs the proof-batch to verify everything works.

=== Usage ===

  cd ~/Desktop/agentmatrix-research
  source .venv/bin/activate
  python research_core/factor_lab/libraries/jq_gm/scripts/export_truth_csv.py

If you have a v78 comparison CSV available, pass it:

  python research_core/factor_lab/libraries/jq_gm/scripts/export_truth_csv.py \
      --comparison-csv path/to/v78_comparison_20260317.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd


# ── The 31 factors verified at v78 (GM vs JQ 100% match) ──
#
# These are the factors that have undergone full cross-validation
# and achieved MISMATCH=0.  Only include these in the truth CSV.
# The remaining 184 factors have no JQ truth data yet.

V78_VERIFIED_FACTORS = [
    # 基础科目及衍生类因子 (12)
    "market_cap",
    "circulating_market_cap",
    "pe_ttm",
    "pe_ratio",
    "pb_mrq",
    "ps_ttm",
    "pcf_ttm",
    "turnover_ratio",
    "total_operating_revenue_ttm",
    "operating_profit_ttm",
    "net_profit_ttm",
    "net_operate_cash_flow_ttm",

    # 质量类因子 (3)
    "roe_ttm",
    "net_profit_margin",
    "roa",

    # 动量类因子 (3)
    "momentum_20d",
    "momentum_60d",
    "REVS20",

    # 成长类因子 (3)
    "operating_revenue_growth_rate",
    "total_asset_growth_rate",
    "net_profit_growth_rate",

    # 技术指标因子 (5)
    "RSI",
    "MACD",
    "MA5",
    "MA20",
    "MA60",

    # 情绪类因子 (3)
    "VOL20",
    "VR",
    "Variance20",

    # 基础扩展 (2)
    "net_working_capital",
    "retained_earnings",
]

# ── 沪深 300 stocks (v78 cross-section: 2026-03-17) ──

HS300_SYMBOLS = [
    "SHSE.000001", "SHSE.000002", "SHSE.000063", "SHSE.000066",
    "SHSE.000100", "SHSE.000157", "SHSE.000166", "SHSE.000301",
    # ... (300 symbols total — fill in from your stock list CSV)
    # Substitute with your actual hs300.csv contents.
]
HS300_DATE = "2026-03-17"


def export_from_comparison_csv(csv_path: str, output_path: str) -> None:
    """Export truth CSV from an existing v78 comparison CSV.

    The comparison CSV has columns like:
      factor_key, symbol, date, gm_value, jq_value, status, ...

    We extract MATCH rows, take jq_value as the truth, and pivot
    to wide format.
    """
    df = pd.read_csv(csv_path)

    # Keep only MATCH rows (verified as correct).
    if "status" in df.columns:
        df = df[df["status"] == "MATCH"]
        print(f"  MATCH rows: {len(df)}")

    # Pivot to wide format.
    truth_wide = df.pivot_table(
        index=["date", "code"],
        columns="factor_name",
        values="jq_value",  # JQ values are the ground truth
    ).reset_index()

    truth_wide.to_csv(output_path, index=False)
    print(f"  Exported: {output_path}")
    print(f"  Shape: {truth_wide.shape}")
    print(f"  Factors: {[c for c in truth_wide.columns if c not in ('date', 'code')]}")


def export_from_gm_terminal(output_path: str) -> None:
    """Export truth CSV by running GM factor computation directly.

    This calls gm_factor_lib.calc_factors() with real securities
    and exports the results.  Use this if you don't have a v78
    comparison CSV but do have the GM terminal running.
    """
    import sys, os
    from pathlib import Path

    _gm_path = os.environ.get("JQ2GM_PATH",
                              str(Path.home() / "Desktop" / "TYDQUANT" / "JQ2GM"))
    sys.path.insert(0, _gm_path)
    from gm_factor_lib import calc_factors  # type: ignore[import]

    stocks_csv = Path(_gm_path) / "hs300.csv"
    if stocks_csv.exists():
        stocks = pd.read_csv(stocks_csv).iloc[:, 0].tolist()
    else:
        print("WARNING: hs300.csv not found. Using demo securities.")
        stocks = ["SHSE.600519", "SZSE.000001", "SHSE.601318", "SZSE.000858"]

    print(f"Computing factors for {len(stocks)} stocks × {len(V78_VERIFIED_FACTORS)} factors...")
    print(f"This may take several minutes depending on your GM terminal speed.")

    result = calc_factors(
        securities=stocks,
        factors=V78_VERIFIED_FACTORS,
        start_date=HS300_DATE,
        end_date=HS300_DATE,
        use_real_price=True,
        skip_paused=True,
    )

    # result: {factor_name: DataFrame(index=trade_date, columns=symbols)}
    # Convert to wide format: date, code, factor_1, factor_2, ...
    frames = []
    for factor_name, df in result.items():
        if df.empty:
            print(f"  WARNING: {factor_name} returned empty DataFrame")
            continue
        stacked = df.stack(future_stack=True).reset_index()
        stacked.columns = ["date", "code", factor_name]
        frames.append(stacked)

    if not frames:
        raise RuntimeError("No factor data returned. Check GM terminal connection.")

    truth_wide = frames[0]
    for frame in frames[1:]:
        truth_wide = truth_wide.merge(frame, on=["date", "code"], how="outer")

    truth_wide.to_csv(output_path, index=False)
    print(f"  Exported: {output_path}")
    print(f"  Shape: {truth_wide.shape}")
    print(f"  Non-null values: {truth_wide.notna().sum().sum()}")


def run_proof_batch(truth_csv_path: str) -> None:
    """Run the full jq_gm proof-batch with the truth CSV."""
    from research_core.factor_lab.cli import main as cli_main

    print("\n" + "=" * 60)
    print("Running jq_gm proof-batch...")
    print("=" * 60)

    # Simulate CLI args.
    import sys as _sys
    _sys.argv = [
        "cli.py",
        "run-jq-gm-proof-batch",
        "--truth-csv", truth_csv_path,
        "--factors", ",".join(V78_VERIFIED_FACTORS),
        "--n-dates", "1",
        "--n-codes", "8",
    ]
    cli_main()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Export JQ truth CSV for jq_gm proof-batch."
    )
    parser.add_argument(
        "--comparison-csv",
        default="",
        help="Path to existing v78 comparison CSV (optional).",
    )
    parser.add_argument(
        "--output",
        default="data/factor_lab/jq_gm_truth.csv",
        help="Output path for truth CSV.",
    )
    parser.add_argument(
        "--run-proof",
        action="store_true",
        help="Run proof-batch after exporting truth CSV.",
    )
    args = parser.parse_args()

    output_path = args.output
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Exporting JQ truth CSV for jq_gm proof-batch")
    print("=" * 60)

    if args.comparison_csv:
        print(f"\nMode: from comparison CSV")
        print(f"  Source: {args.comparison_csv}")
        export_from_comparison_csv(args.comparison_csv, output_path)
    else:
        print(f"\nMode: from GM terminal (live compute)")
        print(f"  Factors: {len(V78_VERIFIED_FACTORS)}")
        print(f"  Date: {HS300_DATE}")
        export_from_gm_terminal(output_path)

    if args.run_proof:
        run_proof_batch(output_path)

    print("\nDone. Next step:")
    print(f"  python -m research_core.factor_lab.cli run-jq-gm-proof-batch \\")
    print(f"    --truth-csv {output_path}")
