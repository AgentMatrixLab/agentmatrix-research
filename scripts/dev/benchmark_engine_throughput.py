"""Measure how long the expression engine takes to compute catalog factor values.

Only the validator was benchmarked (`benchmark_validator_throughput.py`, ~27 s per
factor). The other half of the compute budget -- compiling and evaluating 971
catalog expressions over an all-A panel -- was never measured, and it sits on the
same critical path: if the engine is slow, the shard plan is wrong for a different
reason.

Uses real catalog expressions that reference only fields the panel actually
supplies, so the number reflects the delivery rather than a toy formula.

    python -X utf8 scripts/dev/benchmark_engine_throughput.py
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "dev"))

import rehearse_full_pipeline as rehearsal  # noqa: E402
from research_core.factor_lab.catalog_readiness import classify_expression  # noqa: E402
from research_core.factor_lab.formula_compiler import UnsupportedOperatorError, compile_formula  # noqa: E402

CATALOG = ROOT / "pages" / "factor-db-dashboard" / "data" / "factors.json"
REALISTIC_PANEL_ROWS = 5_400 * 1_900


def pick_expressions(limit: int) -> list[tuple[str, str]]:
    """Runnable catalog expressions with no blocking field references."""
    factors = json.loads(CATALOG.read_text(encoding="utf-8"))["factors"]
    chosen: list[tuple[str, str]] = []
    for factor in factors:
        if len(chosen) >= limit:
            break
        expression = factor["formula_expr"]
        verdict = classify_expression(expression)
        if not verdict.runnable:
            continue
        # Only keep ones the compiler can actually build end to end.
        try:
            compile_formula(expression)
        except UnsupportedOperatorError:
            continue
        except Exception:  # noqa: BLE001
            continue
        chosen.append((factor["factor_id"], expression))
    return chosen


def time_engine(expressions: list[tuple[str, str]], n_codes: int, seed: int) -> dict:
    rehearsal.N_CODES = n_codes
    panel = rehearsal.build_panel(seed)
    # build_panel adds vwap/industry via the extended contract.
    if "industry" not in panel.columns:
        panel["industry"] = "IND00"

    compiled = []
    compile_failures = 0
    started = time.perf_counter()
    for factor_id, expression in expressions:
        try:
            compiled.append((factor_id, compile_formula(expression)))
        except Exception:  # noqa: BLE001
            compile_failures += 1
    compile_seconds = time.perf_counter() - started

    evaluate_started = time.perf_counter()
    evaluated = 0
    evaluate_failures = 0
    for _factor_id, function in compiled:
        try:
            values = function(panel)
            if values is None or len(values) != len(panel):
                evaluate_failures += 1
                continue
            evaluated += 1
        except Exception:  # noqa: BLE001
            evaluate_failures += 1
    evaluate_seconds = time.perf_counter() - evaluate_started

    return {
        "n_codes": n_codes,
        "panel_rows": int(len(panel)),
        "requested": len(expressions),
        "compiled": len(compiled),
        "evaluated": evaluated,
        "compile_failures": compile_failures,
        "evaluate_failures": evaluate_failures,
        "compile_seconds": compile_seconds,
        "evaluate_seconds": evaluate_seconds,
        "total_seconds": compile_seconds + evaluate_seconds,
        "seconds_per_factor": (compile_seconds + evaluate_seconds) / max(evaluated, 1),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expressions", type=int, default=40)
    parser.add_argument("--work-dir", default=".tmp-engine-bench")
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args(argv)

    expressions = pick_expressions(args.expressions)
    if not expressions:
        raise SystemExit("no runnable catalog expressions found")
    print(f"using {len(expressions)} runnable catalog expressions")

    work = ROOT / args.work_dir
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)

    runs = [
        time_engine(expressions[: max(len(expressions) // 2, 1)], 30, seed=3),
        time_engine(expressions, 60, seed=4),
    ]

    print()
    print(f"{'panel rows':>12} {'codes':>6} {'evaluated':>10} {'compile s':>10} {'eval s':>9} {'s/factor':>9}")
    for run in runs:
        print(
            f"{run['panel_rows']:>12,} {run['n_codes']:>6} {run['evaluated']:>10} "
            f"{run['compile_seconds']:>10.1f} {run['evaluate_seconds']:>9.1f} "
            f"{run['seconds_per_factor']:>9.3f}"
        )

    small, large = runs
    row_ratio = large["panel_rows"] / small["panel_rows"]
    cost_ratio = large["seconds_per_factor"] / small["seconds_per_factor"]
    print(
        f"\nscaling: panel grew {row_ratio:.2f}x, seconds per factor grew {cost_ratio:.2f}x"
    )

    # Unlike the validator, expression evaluation is pure vectorised pandas, so it
    # should scale close to linearly in rows. Project on rows and say so.
    projected = large["seconds_per_factor"] * (REALISTIC_PANEL_ROWS / large["panel_rows"])
    print(f"\nprojection to an all-A panel (~{REALISTIC_PANEL_ROWS:,} rows):")
    for label, workers in (("1 core", 1), ("8 cores", 8), ("16 cores", 16)):
        hours = projected * 971 / workers / 3600
        print(f"  {label:>8}: {projected:.2f} s/factor -> 971 factors in {hours:.2f} h")

    print(
        "\nnote: extrapolated from synthetic panels on one machine and linear in rows,\n"
        "      which vectorised pandas makes reasonable but not guaranteed. Confirm on\n"
        "      real data, and note this budget is SEPARATE from the validator's ~27 s/factor."
    )

    failures = small["evaluate_failures"] + large["evaluate_failures"]
    if failures:
        print(f"\nWARNING: {failures} expression(s) failed to evaluate; inspect before trusting the rate")

    (work / "engine_benchmark.json").write_text(
        json.dumps({"runs": runs, "projected_seconds_per_factor": projected}, indent=2),
        encoding="utf-8",
    )
    if not args.keep:
        shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
