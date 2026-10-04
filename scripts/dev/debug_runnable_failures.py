"""Debug why runnable catalog expressions fail to evaluate."""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from research_core.factor_lab.catalog_readiness import classify_expression  # noqa: E402
from research_core.factor_lab.formula_compiler import compile_formula  # noqa: E402

CATALOG = ROOT / "pages" / "factor-db-dashboard" / "data" / "factors.json"


def panel() -> pd.DataFrame:
    rng = np.random.default_rng(1)
    dates = pd.bdate_range("2024-01-01", periods=60)
    frames = []
    for index in range(3):
        close = (10.0 + index) * np.exp(np.cumsum(rng.normal(0.0004, 0.02, len(dates))))
        open_ = close * (1 + rng.normal(0, 0.004, len(dates)))
        high = np.maximum(open_, close) * 1.01
        low = np.minimum(open_, close) * 0.99
        volume = rng.lognormal(14.0, 0.4, len(dates))
        total_turnover = volume * close
        frames.append(
            pd.DataFrame(
                {
                    "date": dates,
                    "code": f"{index:06d}.XSHE",
                    "open": open_,
                    "high": high,
                    "low": low,
                    "close": close,
                    "pre_close": np.concatenate([[close[0]], close[:-1]]),
                    "volume": volume,
                    "total_turnover": total_turnover,
                    "vwap": total_turnover / volume,
                    "amount": total_turnover,
                    "limit_up": close * 1.1,
                    "limit_down": close * 0.9,
                    "circulation_a": 1e8,
                    "total_shares": 1.5e8,
                    "listed_date": pd.Timestamp("2010-01-04"),
                    "de_listed_date": pd.NaT,
                    "is_st": False,
                    "is_suspended": False,
                    "industry": "IND00",
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


def main() -> int:
    frame = panel()
    factors = json.loads(CATALOG.read_text(encoding="utf-8"))["factors"]
    errors: dict[str, list[str]] = {}

    for factor in factors:
        verdict = classify_expression(factor["formula_expr"])
        if not verdict.runnable:
            continue
        try:
            compile_formula(factor["formula_expr"])(frame)
        except Exception as exc:  # noqa: BLE001
            key = f"{type(exc).__name__}: {str(exc)[:60]}"
            errors.setdefault(key, []).append(factor["factor_id"])

    print(f"distinct failures: {len(errors)}")
    for key, ids in sorted(errors.items(), key=lambda kv: -len(kv[1])):
        print(f"\n  x{len(ids):<4} {key}")
        print(f"        e.g. {ids[:3]}")

    print("\n--- full traceback for one of each ---")
    shown = set()
    for factor in factors:
        if not classify_expression(factor["formula_expr"]).runnable:
            continue
        try:
            compile_formula(factor["formula_expr"])(frame)
        except Exception as exc:  # noqa: BLE001
            key = type(exc).__name__
            if key in shown:
                continue
            shown.add(key)
            print(f"\n{factor['factor_id']} :: {factor['formula_expr'][:110]}")
            print("   " + str(exc)[:300])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
