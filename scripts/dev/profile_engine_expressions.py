"""Time each catalog expression individually and explain every evaluation failure.

An aggregate rate hides two things this needs to surface: which expressions are
pathologically slow, and which ones the classifier called runnable but the engine
cannot actually evaluate. The second is the defect class this project keeps
rediscovering -- a readiness test looser than the engine -- so it is reported with
the exception, not counted.

    python -X utf8 scripts/dev/profile_engine_expressions.py
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "dev"))

import rehearse_full_pipeline as rehearsal  # noqa: E402
from research_core.factor_lab.catalog_readiness import classify_expression  # noqa: E402
from research_core.factor_lab.formula_compiler import UnsupportedOperatorError, compile_formula  # noqa: E402

CATALOG = ROOT / "pages" / "factor-db-dashboard" / "data" / "factors.json"


def panel_with_derived(n_codes: int, seed: int) -> pd.DataFrame:
    """The rehearsal panel plus the columns the catalog assumes exist."""
    rehearsal.N_CODES = n_codes
    panel = rehearsal.build_panel(seed)
    if "amount" not in panel.columns:
        panel["amount"] = panel["total_turnover"]
    if "industry" not in panel.columns:
        panel["industry"] = "IND00"
    return panel


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=60, help="how many expressions to profile")
    parser.add_argument("--codes", type=int, default=40)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--slow-seconds", type=float, default=1.0)
    args = parser.parse_args(argv)

    factors = json.loads(CATALOG.read_text(encoding="utf-8"))["factors"]
    panel = panel_with_derived(args.codes, args.seed)
    print(f"panel: {len(panel):,} rows, {panel['code'].nunique()} codes, {panel['date'].nunique()} days")

    timings: list[tuple[str, float]] = []
    failures: list[tuple[str, str, str]] = []
    skipped = 0
    considered = 0

    for factor in factors:
        if considered >= args.limit:
            break
        expression = factor["formula_expr"]
        verdict = classify_expression(expression)
        if not verdict.runnable:
            continue
        considered += 1
        factor_id = factor["factor_id"]
        try:
            function = compile_formula(expression)
        except UnsupportedOperatorError:
            skipped += 1
            continue
        except Exception as exc:  # noqa: BLE001
            failures.append((factor_id, type(exc).__name__ + ": " + str(exc)[:60], expression))
            continue

        started = time.perf_counter()
        try:
            values = function(panel)
            elapsed = time.perf_counter() - started
            if values is None or len(values) != len(panel):
                failures.append((factor_id, f"returned {type(values).__name__} of the wrong length", expression))
                continue
            timings.append((factor_id, elapsed))
        except Exception as exc:  # noqa: BLE001
            failures.append((factor_id, f"{type(exc).__name__}: {str(exc)[:70]}", expression))

    timings.sort(key=lambda item: -item[1])
    print(f"\nprofiled {len(timings)} expression(s); {len(failures)} failed to evaluate; {skipped} skipped")
    print(f"\nslowest {min(12, len(timings))}:")
    for factor_id, elapsed in timings[:12]:
        print(f"  {elapsed:>8.3f}s  {factor_id}")

    if timings:
        total = sum(item[1] for item in timings)
        print(f"\ntotal {total:.1f}s for {len(timings)} expressions")
        print(f"median {np.median([t for _, t in timings]):.3f}s, "
              f"mean {total / len(timings):.3f}s, max {timings[0][1]:.3f}s")

        # Cost is dominated by the tail, so report both a median-based and a
        # mean-based projection rather than one flattering number.
        for label, per_factor in (("median", float(np.median([t for _, t in timings]))),
                                  ("mean", total / len(timings)),
                                  ("max", timings[0][1])):
            scaled = per_factor * (5_400 * 1_900 / len(panel))
            print(f"  project on {label:>6}: {scaled:>10.2f} s/factor -> 971 factors = "
                  f"{scaled * 971 / 3600:>7.1f}h on 1 core, {scaled * 971 / 8 / 3600:>6.1f}h on 8")

        slow = [item for item in timings if item[1] > args.slow_seconds]
        if slow:
            print(f"\n{len(slow)} expression(s) exceeded {args.slow_seconds}s at {len(panel):,} rows:")
            for factor_id, elapsed in slow[:10]:
                print(f"  {elapsed:>8.3f}s  {factor_id}")

    if failures:
        print(f"\nFAILED TO EVALUATE ({len(failures)}) -- the classifier called these runnable:")
        for factor_id, reason, expression in failures[:15]:
            print(f"  {factor_id}")
            print(f"      {reason}")
            print(f"      {expression[:100]}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
