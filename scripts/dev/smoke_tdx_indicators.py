"""Numerically verify the newly added TDX technical indicators.

The panel here is synthetic: this checks that each operator runs and that its
values respect the defining properties of the formula it claims to implement.
It says nothing about predictive power.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from research_core.factor_lab.formula_compiler import compile_formula  # noqa: E402

DATES = pd.bdate_range("2023-01-02", periods=120)


def panel() -> pd.DataFrame:
    rng = np.random.default_rng(20261005)
    frames = []
    for index, code in enumerate(["000001.XSHE", "600000.XSHG", "300750.XSHE"]):
        close = (10.0 + index * 5) * np.exp(np.cumsum(rng.normal(0.0006, 0.02, len(DATES))))
        open_ = close * (1 + rng.normal(0, 0.005, len(DATES)))
        high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0.006, 0.004, len(DATES))))
        low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0.006, 0.004, len(DATES))))
        frames.append(
            pd.DataFrame(
                {
                    "date": DATES,
                    "code": code,
                    "open": open_,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": rng.lognormal(14, 0.5, len(DATES)),
                    "amount": rng.lognormal(18, 0.5, len(DATES)),
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


CASES = [
    ("Variance($close, 20)", "rolling_variance", lambda v: (v >= 0).all(), "variance is non-negative"),
    ("Skewness($close, 20)", "rolling_skewness", lambda v: v.abs().max() < 50, "skewness is bounded"),
    ("Kurtosis($close, 20)", "rolling_kurtosis", lambda v: v.abs().max() < 500, "kurtosis is bounded"),
    ("SharpeRatio($close, 20)", "rolling_sharpe_ratio", lambda v: v.abs().max() < 100, "ratio is bounded"),
    ("Psy($close, 12)", "psychological_line", lambda v: v.between(0, 100).all(), "PSY lies in [0,100]"),
    ("Trix($close, 12)", "triple_exponential_rate", lambda v: v.abs().max() < 50, "TRIX is a percentage"),
    ("Boll_Mid($close, 20)", "ts_mean", lambda v: v.min() > 0, "middle band is a moving average"),
    ("Bbi($close, 3, 6, 12, 24)", "bull_bear_index", lambda v: v.min() > 0, "BBI is a price level"),
    ("Mfi($close, $high, $low, $volume, 14)", "money_flow_index", lambda v: v.between(0, 100).all(), "MFI lies in [0,100]"),
    ("Ar($open, $close, $high, $low, 20)", "popularity_index", lambda v: (v >= 0).all(), "AR is a positive ratio"),
    ("Br($open, $close, $high, $low, 20)", "willingness_index", lambda v: (v >= 0).all(), "BR is a positive ratio"),
    ("Vr($close, $volume, 20)", "volume_ratio", lambda v: (v >= 0).all(), "VR is a positive ratio"),
    ("Cr($close, $high, $low, 20)", "capability_ratio", lambda v: (v >= 0).all(), "CR is a positive ratio"),
]


def main() -> int:
    frame = panel()
    failures = 0
    for expression, label, check, description in CASES:
        try:
            values = pd.Series(compile_formula(expression)(frame))
        except Exception as exc:  # noqa: BLE001
            print(f"  FAIL  {label:<24} {expression} -> {type(exc).__name__}: {exc}")
            failures += 1
            continue

        finite = values.replace([np.inf, -np.inf], np.nan).dropna()
        if finite.empty:
            print(f"  FAIL  {label:<24} produced no finite values")
            failures += 1
            continue
        if not check(finite):
            print(f"  FAIL  {label:<24} violated: {description}")
            failures += 1
            continue
        print(
            f"  OK    {label:<24} n={len(finite):>4}  min={finite.min():>10.4f}  "
            f"max={finite.max():>10.4f}  ({description})"
        )

    print(f"\nfailures: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
