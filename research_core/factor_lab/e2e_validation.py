#!/usr/bin/env python3
"""
End-to-End Validation: Real Data → Factor → Bootstrap CI → Similarity Check.

Demonstrates the complete pipeline:
  1. Fetch real A-share data (akshare → panel format)
  2. Compute Alpha101 factors on real data
  3. Bootstrap 95% CI for IC
  4. Out-of-sample validation
  5. Similarity / duplicate check

Usage:
    /usr/bin/python3 research_core/factor_lab/e2e_validation.py
    /usr/bin/python3 research_core/factor_lab/e2e_validation.py --factors alpha1,alpha2,alpha5
    /usr/bin/python3 research_core/factor_lab/e2e_validation.py --universe csi300 --n-codes 100
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

# Ensure package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from research_core.data_loader.market_data import fetch_real_panel
from research_core.factor_lab.libraries.alpha101 import (
    IMPLEMENTED_ALPHA101_FACTORS,
    compute_alpha101_factors,
)
from research_core.factor_lab.evaluation import (
    build_alpha101_evaluation_report,
    compute_forward_returns,
)
from research_core.factor_lab.inference import (
    bootstrap_ic_confidence_multiple,
    ic_decay_analysis,
    multiple_testing_correction,
    out_of_sample_split,
    out_of_sample_ic_compare,
)
from research_core.factor_lab.similarity import find_similar_factors


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="End-to-end factor validation with real data"
    )
    p.add_argument(
        "--factors", default="alpha1,alpha2,alpha5,alpha10,alpha20",
        help="Comma-separated factor names to test"
    )
    p.add_argument("--start", default="2023-01-01", help="Start date")
    p.add_argument("--end", default="2024-12-31", help="End date")
    p.add_argument("--universe", default="csi300", help="Universe: csi300, csi500, csi800, all")
    p.add_argument("--n-codes", type=int, default=0, help="Sample N codes (0 = no sampling)")
    p.add_argument("--cache", default="/tmp/e2e_ashare_panel.pkl", help="Cache path")
    p.add_argument("--no-cache", action="store_true", help="Force re-fetch")
    p.add_argument("--n-bootstrap", type=int, default=5000, help="Bootstrap resamples")
    p.add_argument("--ci-level", type=float, default=0.95, help="Confidence level")
    return p


def print_section(title: str):
    print(f"\n{'═' * 60}")
    print(f"  {title}")
    print(f"{'═' * 60}")


def format_ci(mean, lower, upper):
    return f"{mean:.5f}  [{lower:.5f}, {upper:.5f}]"


def main():
    args = build_parser().parse_args()
    factor_names = [f.strip() for f in args.factors.split(",")]

    t_total = time.time()

    # ═══════════════════════════════════════════════════════════
    # Step 1: Fetch real data
    # ═══════════════════════════════════════════════════════════
    print_section("Step 1: Fetch Real A-Share Data")
    panel = fetch_real_panel(
        start=args.start,
        end=args.end,
        universe=args.universe,
        sample=args.n_codes if args.n_codes > 0 else None,
        cache_path=args.cache,
        force_refresh=args.no_cache,
        verbose=True,
    )
    print(f"  Panel: {panel['code'].nunique()} stocks × {panel['date'].nunique()} days")
    print(f"  Date range: {panel['date'].min().date()} ~ {panel['date'].max().date()}")
    print(f"  Total rows: {len(panel):,}")

    # ═══════════════════════════════════════════════════════════
    # Step 2: Compute factors
    # ═══════════════════════════════════════════════════════════
    print_section(f"Step 2: Compute Factors ({', '.join(factor_names)})")
    factor_frame = compute_alpha101_factors(panel, factor_names=factor_names)
    print(f"  Factor frame: {len(factor_frame):,} rows")

    # Quick stats
    for fn in factor_names:
        col = factor_frame[fn]
        print(f"  {fn:>12s}: μ={col.mean():.4f}  σ={col.std():.4f}  "
              f"coverage={col.notna().mean():.1%}")

    # ═══════════════════════════════════════════════════════════
    # Step 3: Evaluation (IC + Long/Short)
    # ═══════════════════════════════════════════════════════════
    print_section("Step 3: IC Evaluation")
    eval_report = build_alpha101_evaluation_report(
        panel, factor_frame, factor_names=factor_names
    )
    metrics = eval_report["summary"]["metrics"]

    for fn in factor_names:
        m = metrics[fn]
        print(f"  {fn:>12s}: IC={m['rank_ic_mean']:.5f}  "
              f"IC_IR={m['rank_ic_ir']:.3f}  "
              f"LS={m['long_short_mean']:.5f}  "
              f"Coverage={m['coverage_ratio']:.1%}")

    # ═══════════════════════════════════════════════════════════
    # Step 4: Bootstrap 95% CI
    # ═══════════════════════════════════════════════════════════
    print_section("Step 4: Bootstrap 95% Confidence Intervals")

    # Extract IC series for each factor
    ic_series_dict = {}
    enriched = factor_frame.merge(
        panel[["date", "code", "close"]], on=["date", "code"], how="left"
    )
    enriched["forward_return_1d"] = compute_forward_returns(
        panel.sort_values(["code", "date"]).reset_index(drop=True),
        price_col="close",
    )

    for fn in factor_names:
        ics = []
        for _, group in enriched.groupby("date"):
            valid = group.dropna(subset=[fn, "forward_return_1d"])
            if len(valid) < 20:
                continue
            ic = valid[fn].rank().corr(valid["forward_return_1d"].rank())
            if pd.notna(ic):
                ics.append(ic)
        ic_series_dict[fn] = ics

    bootstrap_results = bootstrap_ic_confidence_multiple(
        ic_series_dict,
        n_bootstrap=args.n_bootstrap,
        ci_level=args.ci_level,
    )

    # Significance summary
    pvalues = {fn: r["p_value"] for fn, r in bootstrap_results.items()}
    fdr = multiple_testing_correction(pvalues, method="fdr_bh", alpha=0.05)

    for fn in factor_names:
        r = bootstrap_results[fn]
        sig = "✅" if r["ic_significant"] else "❌"
        fdr_sig = "✅" if fdr["significant"].get(fn) else "❌"
        print(f"  {fn:>12s}: IC = {format_ci(r['ic_mean'], r['ci_lower'], r['ci_upper'])}")
        print(f"  {'':>12s}  IR = {r['ic_ir']:.3f} [{r['ic_ir_ci'][0]:.3f}, {r['ic_ir_ci'][1]:.3f}]  "
              f"p={r['p_value']:.4f}  raw={sig}  FDR={fdr_sig}  "
              f"Pos={r['ic_positive_ratio']:.1%}")

    print(f"\n  FDR-corrected: {fdr['n_significant']}/{fdr['n_total']} factors significant at α=0.05")

    # ═══════════════════════════════════════════════════════════
    # Step 5: IC Decay Analysis
    # ═══════════════════════════════════════════════════════════
    print_section("Step 5: IC Decay / Stability Analysis")

    for fn in factor_names:
        decay = ic_decay_analysis(
            ic_series_dict[fn],
            window=min(60, len(ic_series_dict[fn]) // 2),
        )
        if "error" in decay:
            print(f"  {fn:>12s}: {decay['error']}")
            continue

        warning = "🔴 DECAYING" if decay["decay_warning"] else "🟢 STABLE"
        print(f"  {fn:>12s}: {warning}  "
              f"slope={decay['trend_slope']:.6f}  "
              f"p={decay['trend_pvalue']:.4f}  "
              f"R²={decay['trend_r_squared']:.3f}  "
              f"1st={decay['first_half_mean']:.5f}  "
              f"2nd={decay['second_half_mean']:.5f}  "
              f"half_life={decay['half_life_days']}d")

    # ═══════════════════════════════════════════════════════════
    # Step 6: Out-of-Sample Validation
    # ═══════════════════════════════════════════════════════════
    print_section("Step 6: Out-of-Sample Validation")

    fwd_returns = enriched["forward_return_1d"]
    for fn in factor_names:
        oos = out_of_sample_ic_compare(
            enriched, fwd_returns, fn, train_ratio=0.7
        )
        is_r = oos["in_sample"]
        oos_r = oos["out_of_sample"]
        if is_r and oos_r:
            warning = "🔴 OVERFIT" if oos["overfit_warning"] else "🟢 OK"
            print(f"  {fn:>12s}: IS_IC={is_r['ic_mean']:.5f}  "
                  f"OOS_IC={oos_r['ic_mean']:.5f}  "
                  f"decay={oos['decay_ratio']:.2f}  {warning}")

    # ═══════════════════════════════════════════════════════════
    # Step 7: Similarity / Duplicate Check
    # ═══════════════════════════════════════════════════════════
    print_section("Step 7: Factor Similarity (Duplicate Detection)")

    # Build existing_frames dict
    existing = {fn: factor_frame[["date", "code", fn]] for fn in factor_names}

    # Check each factor against all others
    for fn in factor_names:
        report = find_similar_factors(
            factor_frame, fn, existing, threshold=0.7
        )
        above = report["above_threshold"]
        if above:
            matches = ", ".join(
                f"{m['factor_name']}(ρ={m['abs_correlation']:.3f})"
                for m in above
            )
            print(f"  {fn:>12s}: 🔴 DUPLICATES: {matches}")
        elif report["top_match"]:
            print(f"  {fn:>12s}: 🟢 Unique (closest: {report['top_match']} "
                  f"ρ={report['top_correlation']:.3f})")
        else:
            print(f"  {fn:>12s}: 🟢 Unique (no matches)")

    # ═══════════════════════════════════════════════════════════
    # Summary
    # ═══════════════════════════════════════════════════════════
    total_elapsed = time.time() - t_total
    print_section("Pipeline Complete")
    print(f"  Time: {total_elapsed:.0f}s")
    print(f"  Factors: {len(factor_names)}")
    print(f"  Stocks: {panel['code'].nunique()}")
    print(f"  Dates: {panel['date'].nunique()}")
    print(f"  Significant (FDR): {fdr['n_significant']}/{fdr['n_total']}")

    # Export results
    output = {
        "pipeline": "e2e_validation",
        "config": {
            "factors": factor_names,
            "start": args.start,
            "end": args.end,
            "universe": args.universe,
            "n_codes": panel["code"].nunique(),
            "n_dates": panel["date"].nunique(),
            "n_bootstrap": args.n_bootstrap,
            "ci_level": args.ci_level,
        },
        "bootstrap": bootstrap_results,
        "fdr_correction": fdr,
        "elapsed_seconds": round(total_elapsed, 1),
    }

    out_path = "/tmp/e2e_validation_results.json"
    with open(out_path, "w") as f:
        json.dump(output, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n  Results saved to: {out_path}")


if __name__ == "__main__":
    main()
