#!/usr/bin/env python3
"""CI regression gate for jq_gm factor library — unified stub + GM path.

=== TWO PATHS ===

Path A (stub — Mac / CI):
  Uses mining_bridge.batch_verify() on auto-generated expression set covering
  all 7 mappable pattern types with multiple window parameters.
  Baseline: scripts/jq_gm_regression_baseline_stub.json
  Detects: changes in bridge parsing/computation logic.
  Does NOT verify: numerical correctness of GM factor values.

Path B (GM — Windows VM with GM SDK):
  Uses gm_factor_lib.calc_factors() on ALL registered jq_gm factors.
  Baseline: scripts/jq_gm_regression_baseline_gm.json (generated on VM).
  Detects: changes in GM factor computation output (code or API behaviour).
  Requires: GM SDK token (argv[1]), gm_factor_lib on sys.path.

New factors/expressions are automatically included — baseline is regenerated
from the actual registered factor list / pattern table, not a hardcoded list.

Auto-detection: tries 'from gm_factor_lib import calc_factors'.
  Succeeds → Path B (real GM).
  Fails    → Path A (stub).

=== Usage ===

  # Path A (Mac / CI):
  python scripts/check_regression.py

  # Path A — regenerate stub baseline:
  python scripts/check_regression.py --generate

  # Path B (VM):
  python scripts/check_regression.py <GM_TOKEN>

  # Path B — regenerate GM baseline on VM:
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
# Path A: Stub mode — auto-generate expressions from pattern table
# ═══════════════════════════════════════════════════════════════

# Expression templates keyed by mappable ExprType, with window params.
# Each template is a callable (window) -> expression string.
# CROSS_SECTIONAL excluded (always unmappable, no meaningful regression check).
_PATH_A_TEMPLATES: list[tuple[str, list[int]]] = [
    # (expression_template, [window_values])
    ("Ref($close, {w}) / $close - 1",         [5, 10, 20, 60]),        # MOMENTUM
    ("$close / Ref($close, {w}) - 1",         [5, 20]),                # MOMENTUM-alt
    ("$volume / Mean($volume, {w})",          [5, 10, 20]),            # VOLUME_RATIO
    ("Std($close, {w})",                     [5, 10, 20]),            # VOLATILITY
    ("Std(Ref($close, 1) / $close, {w})",     [5, 10, 20]),            # VOLATILITY-returns
    ("Mean($close, {w})",                    [5, 10, 20, 60]),         # MOVING_AVERAGE
    ("$high / $low",                          []),                      # PRICE_RATIO (no window)
    ("Corr($close, $volume, {w})",            [10, 20]),               # CORRELATION
    ("$close - Ref($close, {w})",             [5, 10, 20]),            # DELTA
]


def _path_a_generate_expressions() -> list[str]:
    exprs = []
    for template, windows in _PATH_A_TEMPLATES:
        if not windows:
            exprs.append(template)
        else:
            for w in windows:
                exprs.append(template.format(w=w))
    return exprs


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
    from research_core.factor_lab.libraries.ai_factors.factors import compute_expressions
    panel = _gen_demo_panel()
    exprs = _path_a_generate_expressions()
    result = compute_expressions(panel, exprs)
    flat = {}
    for col in result.columns:
        if col in ("date", "code"):
            continue
        vals = result[col].dropna()
        if len(vals) > 0:
            flat[col] = {
                "count": int(len(vals)),
                "mean": float(vals.mean()),
            }
    return flat


def _path_a_check(baseline: dict, current: dict) -> int:
    failures = 0
    for expr, bl in baseline.items():
        cur = current.get(expr)
        if cur is None:
            print(f"  MISSING: {expr}")
            failures += 1
            continue
        cc = abs(cur["count"] - bl["count"]) / max(bl["count"], 1)
        if cc > REGRESSION_THRESHOLD:
            print(f"  COUNT: {expr}: {bl['count']} -> {cur['count']} ({cc:.1%})")
            failures += 1
            continue
        mc = abs(cur["mean"] - bl["mean"]) / max(abs(bl["mean"]), 1e-10)
        if mc > REGRESSION_THRESHOLD:
            print(f"  MEAN:  {expr}: {bl['mean']:.4f} -> {cur['mean']:.4f} ({mc:.1%})")
            failures += 1
            continue
    new = set(current.keys()) - set(baseline.keys())
    if new:
        print(f"  NEW expressions ({len(new)}): {sorted(new)[:5]}...")
        print(f"  Run --generate to update baseline.")
        failures += len(new)
    return failures


# ═══════════════════════════════════════════════════════════════
# Path B: Real GM SDK — auto-generate from FACTOR_REGISTRY
# ═══════════════════════════════════════════════════════════════

_PATH_B_STOCKS = [
    "SHSE.600519", "SHSE.600036", "SHSE.601318", "SHSE.600900", "SHSE.601166",
    "SHSE.600887", "SHSE.601398", "SHSE.600809", "SZSE.000858", "SZSE.000651",
    "SZSE.000333", "SZSE.002415", "SZSE.300750", "SZSE.000001", "SZSE.000568",
    "SHSE.601012", "SHSE.600276", "SHSE.601899", "SHSE.600585", "SHSE.601668",
]


def _path_b_get_factors() -> list[str]:
    """Read all registered jq_gm factor names from the actual registry."""
    try:
        # Prefer AgentMatrix JQ_GM_IMPLEMENTED_FACTORS if importable
        from research_core.factor_lab.libraries.jq_gm import JQ_GM_IMPLEMENTED_FACTORS
        return sorted(JQ_GM_IMPLEMENTED_FACTORS)
    except ImportError:
        pass
    try:
        # Fallback: read from gm_factor_lib FACTOR_REGISTRY
        from gm_factor_lib import FACTOR_REGISTRY
        return sorted(FACTOR_REGISTRY.keys())
    except ImportError:
        pass
    print("ERROR: cannot determine factor list. Import failed.")
    sys.exit(2)


def _path_b_compute(token: str) -> dict:
    _gm_set_token(token)
    factors = _path_b_get_factors()
    result = _gm_calc(
        securities=_PATH_B_STOCKS, factors=factors,
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
    # Detect new factors not in baseline
    new = set(current.keys()) - set(baseline.keys())
    if new:
        print(f"  NEW factors ({len(new)}): {sorted(new)[:5]}...")
        print(f"  Run --generate on VM to update baseline.")
        failures += len(new)
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
        print(f"Factors: {len(_path_b_get_factors())} from FACTOR_REGISTRY")
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
            current = _path_a_compute()
            out = {
                "_meta": {
                    "description": "Auto-generated stub regression baseline.",
                    "note": "Detects code changes, NOT correctness.",
                    "seed": SEED, "n_dates": N_DATES, "n_codes": N_CODES,
                    "expression_count": len(current),
                },
                "expressions": current,
            }
            baseline_path.write_text(json.dumps(out, indent=2))
            print(f"Baseline generated: {len(current)} expressions -> {baseline_path}")
            return 0

        if not baseline_path.exists():
            print(f"ERROR: no stub baseline at {baseline_path}")
            print("Run with --generate to create it.")
            return 1

        baseline = json.loads(baseline_path.read_text())
        meta = baseline.get("_meta", {})
        print(f"Baseline: {meta.get('n_dates')}d x {meta.get('n_codes')}c, "
              f"{meta.get('expression_count', '?')} expressions")
        current_raw = _path_a_compute()
        current = current_raw
        bl_factors = baseline.get("expressions", baseline.get("factors", baseline))
        failures = _path_a_check(bl_factors, current)

    if failures == 0:
        print(f"PASSED: stable within {REGRESSION_THRESHOLD:.0%}")
        return 0
    print(f"FAILED: {failures} regression(s)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
