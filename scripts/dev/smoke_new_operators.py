"""Verify the newly implemented operators actually execute and are numerically sane.

Read-only except for building an in-memory panel. The panel here is synthetic:
this checks that the operators *run and behave*, never that a factor predicts
anything.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from research_core.factor_lab.formula_compiler import compile_formula  # noqa: E402

DATES = pd.bdate_range("2023-01-02", periods=80)


def panel() -> pd.DataFrame:
    rng = np.random.default_rng(20261005)
    frames = []
    for index, code in enumerate(["000001.XSHE", "600000.XSHG", "300750.XSHE"]):
        close = 10.0 * np.exp(np.cumsum(rng.normal(0.0005, 0.02, len(DATES))))
        high = close * (1 + np.abs(rng.normal(0.006, 0.004, len(DATES))))
        low = close * (1 - np.abs(rng.normal(0.006, 0.004, len(DATES))))
        open_ = close * (1 + rng.normal(0, 0.004, len(DATES)))
        frames.append(
            pd.DataFrame(
                {
                    "date": DATES,
                    "code": code,
                    "open": open_,
                    "high": np.maximum.reduce([high, open_, close]),
                    "low": np.minimum.reduce([low, open_, close]),
                    "close": close,
                    "volume": rng.lognormal(14, 0.4, len(DATES)),
                    "amount": rng.lognormal(18, 0.4, len(DATES)),
                    "industry": ["bank"] * len(DATES),
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


CASES = [
    ("EMA($close, 12)", "ts_ema"),
    ("Slope($close, 20)", "rolling_slope"),
    ("Rsquare($close, 20)", "rolling_rsquare"),
    ("Resi($close, 20)", "rolling_resi"),
    ("Quantile($close, 20, 0.8)", "rolling_quantile"),
    ("IdxMax($high, 20)", "rolling_idxmax"),
    ("IdxMin($low, 20)", "rolling_idxmin"),
    ("Bias($close, 6)", "bias"),
    ("RSI($close, 14)", "relative_strength_index"),
    ("Boll_Up($close, 20, 2.0)", "bollinger_band_upper"),
    ("Boll_Dn($close, 20, 2.0)", "bollinger_band_lower"),
    ("ATR($close, $high, $low, 14)", "true_range"),
    ("CCI($close, $high, $low, 20)", "commodity_channel_index"),
    ("Corr($close, $volume, 6)", "rolling_corr"),
]


def main() -> int:
    frame = panel()
    failures = 0
    for expression, label in CASES:
        try:
            values = compile_formula(expression)(frame)
        except Exception as exc:  # noqa: BLE001
            print(f"  FAIL  {label:<24} {expression}  -> {type(exc).__name__}: {exc}")
            failures += 1
            continue

        values = pd.Series(values)
        finite = values.replace([np.inf, -np.inf], np.nan).dropna()
        if finite.empty:
            print(f"  FAIL  {label:<24} produced no finite values")
            failures += 1
            continue
        print(
            f"  OK    {label:<24} n={len(finite):>4}  "
            f"min={finite.min():>10.4f}  max={finite.max():>10.4f}  mean={finite.mean():>9.4f}"
        )

    print(f"\nfailures: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
