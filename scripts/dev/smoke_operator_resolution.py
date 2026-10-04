"""Smoke-check the operator spelling resolver across the catalog's conventions."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from research_core.factor_lab import formula_compiler as fc  # noqa: E402

CASES = [
    ("Ref($close, 5)", True),
    ("Ts_Mean($close, 5)", True),
    ("Ts_Std($close, 20)", True),
    ("Ts_Min($low, 5)", True),
    ("Ts_Max($high, 5)", True),
    ("Ts_Sum($volume, 5)", True),
    ("Ts_Rank($close, 5)", True),
    ("Ts_ArgMax($high, 5)", True),
    ("Ts_ArgMin($low, 5)", True),
    ("Ts_Product($volume, 3)", True),
    ("Ts_DecayLinear($close, 5)", True),
    ("DecayLinear($close, 5)", True),
    ("Correlation(rank($close), rank($volume), 6)", True),
    ("Covariance($close, $volume, 6)", True),
    ("StdDev($close, 20)", True),
    ("Mean($close, 5)", True),
    ("Rank($close)", True),
    ("Power($close, 2)", True),
    ("SignedPower($close, 2)", True),
    ("IndNeutral($close, industry)", True),
    ("Greater($close, $open)", False),   # semantics unverified -> must stay blocked
    ("Less($close, $open)", False),
    ("Ema($close, 12)", False),          # genuinely unimplemented
    ("Quantile($close, 0.5, 20)", False),
]


def main() -> int:
    print(f"operator index entries: {len(fc._OPERATOR_INDEX)}")
    failures = 0
    for expression, should_compile in CASES:
        try:
            fc.compile_formula(expression)
            got = True
            detail = ""
        except Exception as exc:  # noqa: BLE001
            got = False
            detail = f"{type(exc).__name__}: {str(exc)[:60]}"
        mark = "OK  " if got == should_compile else "BAD "
        if got != should_compile:
            failures += 1
        print(f"  {mark} compile={str(got):5} expected={str(should_compile):5}  {expression}"
              + (f"   [{detail}]" if detail else ""))
    print(f"\nmismatches: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
