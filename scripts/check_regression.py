#!/usr/bin/env python3
"""CI regression gate for jq_gm factor library.

Compares current code output against a deterministic baseline stored in the
repository.  The baseline was generated in stub mode (no GM SDK) with fixed
seed, so it detects CODE CHANGES but does NOT verify numerical correctness.

Real verification requires GM SDK + JQ truth data on a VM.

Usage:
    python scripts/check_regression.py

Returns exit code 0 if no regression, 1 if regression detected.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from research_core.factor_lab.mining_bridge import batch_verify

BASELINE_PATH = Path(__file__).resolve().parent / "jq_gm_regression_baseline.json"
N_DATES = 60
N_CODES = 20
SEED = 42
REGRESSION_THRESHOLD = 0.05  # 5%


def _gen_demo_panel() -> pd.DataFrame:
    rng = np.random.default_rng(SEED)
    dates = pd.date_range("2025-01-01", periods=N_DATES, freq="B")
    codes = [f"DEMO_{i:04d}" for i in range(N_CODES)]
    idx = pd.MultiIndex.from_product([dates, codes], names=["date", "code"])
    return pd.DataFrame(
        {
            "open": rng.uniform(10, 100, len(idx)),
            "high": rng.uniform(10, 100, len(idx)),
            "low": rng.uniform(10, 100, len(idx)),
            "close": rng.uniform(10, 100, len(idx)),
            "volume": rng.uniform(1e4, 1e7, len(idx)),
        },
        index=idx,
    ).reset_index()


def main() -> int:
    print("=== jq_gm Regression Check ===")

    if not BASELINE_PATH.exists():
        print(f"ERROR: baseline not found at {BASELINE_PATH}")
        print("Run once with GM SDK to generate, or check into repo.")
        return 1

    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    meta = baseline.get("_meta", {})
    print(f"Baseline: {meta.get('n_dates')}d x {meta.get('n_codes')}c, seed={meta.get('seed')}")
    print(f"Note: {meta.get('note', '')}")

    expressions = list(baseline["factors"].keys())
    panel = _gen_demo_panel()

    try:
        results = batch_verify(expressions, panel)
    except Exception as e:
        print(f"COMPUTATION ERROR: {e}")
        return 1

    current = {}
    for r in results:
        current[r.expression] = {
            "status": r.status,
            "finite_count": r.finite_count,
            "finite_ratio": round(r.finite_ratio, 6),
        }

    failures = 0
    for expr, bl in baseline["factors"].items():
        cur = current.get(expr)
        if cur is None:
            print(f"  MISSING: {expr}")
            failures += 1
            continue

        if cur["status"] != bl["status"]:
            print(f"  STATUS CHANGE: {expr}: {bl['status']} → {cur['status']}")
            failures += 1
            continue

        if bl["finite_count"] > 0:
            count_change = abs(cur["finite_count"] - bl["finite_count"]) / bl["finite_count"]
            if count_change > REGRESSION_THRESHOLD:
                print(f"  COUNT: {expr}: {bl['finite_count']} → {cur['finite_count']} ({count_change:.1%})")
                failures += 1
                continue

        if bl["finite_ratio"] > 0:
            ratio_change = abs(cur["finite_ratio"] - bl["finite_ratio"]) / bl["finite_ratio"]
            if ratio_change > REGRESSION_THRESHOLD:
                print(f"  RATIO: {expr}: {bl['finite_ratio']:.4f} → {cur['finite_ratio']:.4f} ({ratio_change:.1%})")
                failures += 1
                continue

    if failures == 0:
        print(f"PASSED: {len(expressions)} expressions stable within {REGRESSION_THRESHOLD:.0%}")
        return 0

    print(f"FAILED: {failures} regression(s) detected")
    return 1


if __name__ == "__main__":
    sys.exit(main())
