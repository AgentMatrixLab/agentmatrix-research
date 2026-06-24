#!/usr/bin/env python3
"""CI regression gate for jq_gm factor library — unified stub + GM path.

=== TWO PATHS ===

Path A (stub — Mac / CI):
  Uses mining_bridge.batch_verify() to check expression parsing stability.
  Baseline: scripts/jq_gm_regression_baseline_stub.json
  Detects: changes in bridge parsing/computation logic.
  Does NOT verify: numerical correctness of GM factor values.

Path B (GM — Windows VM with GM SDK):
  Uses gm_factor_lib.calc_factors() to compute REAL factor values via GM API.
  Baseline: scripts/jq_gm_regression_baseline_gm.json (generated on VM).
  Detects: changes in GM factor computation output (code or API behaviour).
  Requires: GM SDK token (argv[1]), gm_factor_lib on sys.path.

Auto-detection: tries 'from gm_factor_lib import calc_factors'.
  Succeeds → Path B (real GM).
  Fails    → Path A (stub).

=== Usage ===

  # Path A (Mac / CI):
  python scripts/check_regression.py

  # Path B (VM):
  python scripts/check_regression.py <GM_TOKEN>

  # Regenerate baseline (Path B only):
  python scripts/check_regression.py <GM_TOKEN> --generate

Returns exit code 0 if no regression, 1 if regression detected.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
BASELINE_STUB = SCRIPT_DIR / "jq_gm_regression_baseline_stub.json"
BASELINE_GM   = SCRIPT_DIR / "jq_gm_regression_baseline_gm.json"
N_DATES = 60
N_CODES = 20
N_STOCKS_VM = 20
SEED = 42
REGRESSION_THRESHOLD = 0.05

# ── Auto-detect: Path A or Path B? ──────────────────────────
_GM_READY = False
try:
    from gm.api import set_token as _gm_set_token
    from gm_factor_lib import calc_factors as _gm_calc
    _GM_READY = True
except ImportError:
    pass


# ═══════════════════════════════════════════════════════════════
# Path A: Stub mode (Mac / CI)
# ═══════════════════════════════════════════════════════════════

def _gen_demo_panel() -> pd.DataFrame:
    rng = np.random.default_rng(SEED)
    dates = pd.date_range("2025-01-01", periods=N_DATES, freq="B")
    codes = [f"DEMO_{i:04d}" for i in range(N_CODES)]
    idx = pd.MultiIndex.from_product([dates, codes], names=["date", "code"])
    return pd.DataFrame({
        "open": rng.uniform(10, 100, len(idx)),
        "high": rng.uniform(10, 100, len(idx)),
        "low": rng.uniform(10, 100, len(idx)),
        "close": rng.uniform(10, 100, len(idx)),
        "volume": rng.uniform(1e4, 1e7, len(idx)),
    }, index=idx).reset_index()


def _path_a_compute() -> dict:
    from research_core.factor_lab.mining_bridge import batch_verify
    exprs = [
        "Ref($close, 5) / $close - 1",
        "Ref($close, 20) / $close - 1",
        "$volume / Mean($volume, 10)",
        "Std(Ref($close, 1) / $close, 10)",
        "Mean($close, 20)",
        "$high / $low",
        "$close - Ref($close, 10)",
    ]
    panel = _gen_demo_panel()
    results = batch_verify(exprs, panel)
    return {
        r.expression: {
            "status": r.status,
            "finite_count": r.finite_count,
            "finite_ratio": round(r.finite_ratio, 6),
        }
        for r in results
    }


def _path_a_check(baseline: dict, current: dict) -> int:
    failures = 0
    for expr, bl in baseline.items():
        cur = current.get(expr)
        if cur is None:
            print(f"  MISSING: {expr}")
            failures += 1
            continue
        if cur["status"] != bl["status"]:
            print(f"  STATUS: {expr}: {bl['status']} -> {cur['status']}")
            failures += 1
            continue
        if bl["finite_count"] > 0:
            c = abs(cur["finite_count"] - bl["finite_count"]) / bl["finite_count"]
            if c > REGRESSION_THRESHOLD:
                print(f"  COUNT: {expr}: {bl['finite_count']} -> {cur['finite_count']} ({c:.1%})")
                failures += 1
                continue
        if bl["finite_ratio"] > 0:
            c = abs(cur["finite_ratio"] - bl["finite_ratio"]) / bl["finite_ratio"]
            if c > REGRESSION_THRESHOLD:
                print(f"  RATIO: {expr}: {bl['finite_ratio']:.4f} -> {cur['finite_ratio']:.4f} ({c:.1%})")
                failures += 1
                continue
    return failures


# ═══════════════════════════════════════════════════════════════
# Path B: Real GM SDK (VM)
# ═══════════════════════════════════════════════════════════════

_PATH_B_FACTORS = [
    "market_cap", "pe_ttm", "pb_ratio", "roe_ttm", "roa",
    "gross_profit_margin", "net_profit_margin",
    "momentum_120d", "momentum_252d", "volatility_120d",
    "total_assets_growth_rate", "net_profit_growth_per_share",
    "KDJ_K", "KDJ_D", "RSI",
    "net_operate_cash_flow", "bps",
]

_PATH_B_STOCKS = [
    "SHSE.600519", "SHSE.600036", "SHSE.601318", "SHSE.600900", "SHSE.601166",
    "SHSE.600887", "SHSE.601398", "SHSE.600809", "SZSE.000858", "SZSE.000651",
    "SZSE.000333", "SZSE.002415", "SZSE.300750", "SZSE.000001", "SZSE.000568",
    "SHSE.601012", "SHSE.600276", "SHSE.601899", "SHSE.600585", "SHSE.601668",
]


def _path_b_compute(token: str) -> dict:
    _gm_set_token(token)
    result = _gm_calc(
        securities=_PATH_B_STOCKS, factors=_PATH_B_FACTORS,
        start_date="2025-12-31", end_date="2025-12-31",
        use_real_price=True, skip_paused=True,
    )
    flat = {}
    for factor_name, df in result.items():
        vals = []
        for col in df.columns:
            v = df[col].iloc[0] if len(df) > 0 else None
            if v is not None and str(v) != "nan":
                vals.append(float(v))
        if vals:
            flat[factor_name] = {
                "count": len(vals),
                "mean": sum(vals) / len(vals),
            }
    return flat


def _path_b_check(baseline: dict, current: dict) -> int:
    failures = 0
    for fk, bl in baseline.items():
        cur = current.get(fk)
        if cur is None:
            print(f"  MISSING: {fk}")
            failures += 1
            continue
        cc = abs(cur["count"] - bl["count"]) / max(bl["count"], 1)
        if cc > REGRESSION_THRESHOLD:
            print(f"  COUNT: {fk}: {bl['count']} -> {cur['count']} ({cc:.1%})")
            failures += 1
            continue
        mc = abs(cur["mean"] - bl["mean"]) / max(abs(bl["mean"]), 1e-10)
        if mc > REGRESSION_THRESHOLD:
            print(f"  MEAN:  {fk}: {bl['mean']:.4f} -> {cur['mean']:.4f} ({mc:.1%})")
            failures += 1
            continue
    return failures


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════

def main() -> int:
    generate = "--generate" in sys.argv
    token = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else ""

    if _GM_READY and token:
        # ── Path B: Real GM ──
        print("=== jq_gm Regression Check (Path B: GM SDK) ===")
        baseline_path = BASELINE_GM

        if generate:
            current = _path_b_compute(token)
            baseline_path.write_text(json.dumps(current, indent=2))
            print(f"Baseline generated: {len(current)} factors -> {baseline_path}")
            return 0

        if not baseline_path.exists():
            print(f"ERROR: no GM baseline at {baseline_path}")
            print("Run with --generate on VM to create it.")
            return 1

        baseline = json.loads(baseline_path.read_text())
        current = _path_b_compute(token)
        failures = _path_b_check(baseline, current)
    else:
        # ── Path A: Stub ──
        print("=== jq_gm Regression Check (Path A: stub) ===")
        baseline_path = BASELINE_STUB

        if generate:
            print("--generate not supported in stub mode. Baseline is committed.")
            return 0

        if not baseline_path.exists():
            print(f"ERROR: no stub baseline at {baseline_path}")
            return 1

        baseline = json.loads(baseline_path.read_text())
        print(f"Baseline: {baseline['_meta'].get('n_dates')}d x {baseline['_meta'].get('n_codes')}c")
        current_raw = _path_a_compute()
        current = {k: v for k, v in current_raw.items() if k in baseline.get("factors", baseline)}
        if "factors" in baseline:
            bl_factors = baseline["factors"]
        else:
            bl_factors = baseline
        failures = _path_a_check(bl_factors, current)

    if failures == 0:
        print(f"PASSED: stable within {REGRESSION_THRESHOLD:.0%}")
        return 0
    print(f"FAILED: {failures} regression(s)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
