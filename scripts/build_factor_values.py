"""Build the factor-values dataset the frozen validator consumes.

This was missing. `validate-batch` takes `--factor-file`, and the only code that
produced one lived in test fixtures and rehearsal scripts. In a real run there
would have been no factor file at all -- or, worse, one built without the
perturbation variants, in which case EVERY candidate records
`parameter_perturbation` as unmeasured, the gate is not passed, and the delivery
yields zero factors. The 300 target would have failed at the last gate for a
purely mechanical reason.

The perturbation contract, read off the frozen gate: for each multiplier in
`configs/validation_gates.yaml`, the gate looks up the name
``<factor_id>|window=<max(1, round(base_window * multiplier))>`` and, finding
nothing, records the gate as unmeasured and NOT passed. Two consequences drive
this script:

* The variant windows must be derived with **exactly** the gate's arithmetic,
  including its ``max(1, ...)`` clamp, or the names will not match.
* A variant entry is written **even when its window equals the base window.**
  For a base of 2, both 0.8 and 1.2 round back to 2; 37 of the 849 windowed
  catalog candidates are in that position. Skipping the entry because "it is the
  same factor" leaves the gate unmeasured and rejects the candidate.

That second case is a real weakness in the frozen gate -- a perturbation that
cannot move the parameter proves nothing -- so it is counted and reported rather
than quietly satisfied.

    python -X utf8 scripts/build_factor_values.py \
        --candidates data/factor_lab/candidate_list.csv \
        --panel-file data/factor_lab/validation_panel.parquet \
        --config configs/validation_gates.yaml \
        --output data/factor_lab/factor_values.parquet
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research_core.factor_lab.batch_validation import load_candidate_list  # noqa: E402
from research_core.factor_lab.formula_compiler import (  # noqa: E402
    UnsupportedOperatorError,
    compile_formula,
)
from research_core.factor_lab.precomputed_factors import (  # noqa: E402
    DATASET,
    perturbation_factor_name,
)

CN_TZ = timezone(timedelta(hours=8))
VALUE_DEFINITION = (
    "Cross-sectional factor value per (date, code), computed by the repository's own "
    "expression engine from the panel named in the source field. Perturbation variants "
    "are carried under '<factor_id>|window=<w>' for every multiplier in the frozen config."
)


class FactorValueError(RuntimeError):
    """Raised when the factor-value dataset cannot be built."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def substitute_window(expression: str, old: int, new: int) -> tuple[str, int]:
    """Replace the window literal, returning the new expression and how many changed.

    Every standalone occurrence is replaced, because a factor that uses its window
    in three places uses ONE parameter and perturbing it should move all three.
    The count is returned so a factor whose window value also appears as an
    unrelated constant can be spotted in the report rather than assumed away.
    """
    pattern = re.compile(rf"(?<![0-9A-Za-z_.]){old}(?![0-9A-Za-z_.])")
    replaced, count = pattern.subn(str(new), expression)
    return replaced, count


def variant_windows(base_window: int, multipliers: list[float]) -> list[int]:
    """The exact arithmetic the frozen gate uses to ask for a variant.

    Deduplicated: when two multipliers round to the same window -- base 2 sends
    both 0.8 and 1.2 to 2 -- asking for the same series twice would write the row
    twice and the validator rejects duplicate (date, code, factor_name) keys.
    """
    return sorted({max(1, int(round(base_window * float(m)))) for m in multipliers})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--candidates", required=True)
    parser.add_argument("--panel-file", required=True)
    parser.add_argument("--config", default="configs/validation_gates.yaml")
    parser.add_argument("--output", required=True)
    parser.add_argument("--sidecar", default="", help="defaults to <output>.json")
    parser.add_argument("--code-column", default="code")
    parser.add_argument("--date-column", default="date")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--report", default="", help="where to write the build report JSON")
    args = parser.parse_args(argv)

    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    multipliers = [float(m) for m in config["perturbation"]["multipliers"]]
    candidates = load_candidate_list(args.candidates)
    if args.limit:
        candidates = candidates[: args.limit]
    print(f"candidates: {len(candidates)}   multipliers: {multipliers}")

    panel = pd.read_parquet(args.panel_file)
    for column in (args.date_column, args.code_column):
        if column not in panel.columns:
            raise FactorValueError(f"panel is missing the {column!r} column")
    panel = panel.copy()
    # The engine reads 成交额 as total_turnover; older panels call it amount.
    if "total_turnover" not in panel.columns and "amount" in panel.columns:
        panel["total_turnover"] = panel["amount"]
    print(f"panel: {len(panel):,} rows, {panel[args.code_column].nunique()} codes, "
          f"{panel[args.date_column].nunique()} dates")

    dates = pd.to_datetime(panel[args.date_column])
    codes = panel[args.code_column].astype(str)

    frames: list[pd.DataFrame] = []
    factors_meta: dict[str, dict] = {}
    failures: list[tuple[str, str]] = []
    vacuous: list[str] = []
    ambiguous: list[tuple[str, int]] = []
    started = time.perf_counter()

    for position, candidate in enumerate(candidates, start=1):
        factor_id = candidate.factor_id
        metadata = candidate.metadata or {}
        expression = metadata.get("formula", "")
        if not expression:
            failures.append((factor_id, "candidate carries no formula"))
            continue
        base_window = candidate.window
        if base_window is None:
            # Not merely at risk: the sidecar contract requires every declared
            # factor to carry a positive integer window, so a windowless factor
            # cannot be represented in this file at all, and the validator cannot
            # obtain a base window for it. Excluding it here is the honest
            # outcome; silently emitting a series the sidecar cannot declare would
            # fail later with a much less obvious message.
            failures.append((
                factor_id,
                "no window: the factor file cannot declare a windowless factor, "
                "so this candidate cannot be validated (see Q11)",
            ))
            continue

        try:
            base_values = pd.Series(compile_formula(expression)(panel))
        except UnsupportedOperatorError as exc:
            failures.append((factor_id, f"unsupported operator: {exc}"))
            continue
        except Exception as exc:  # noqa: BLE001
            failures.append((factor_id, f"{type(exc).__name__}: {exc}"))
            continue

        frames.append(pd.DataFrame({
            args.date_column: dates, args.code_column: codes,
            "factor_name": factor_id, "value": base_values.to_numpy(dtype=float),
        }))
        factors_meta[factor_id] = {"window": int(base_window)}

        windows = variant_windows(int(base_window), multipliers)
        if all(window == int(base_window) for window in windows):
            vacuous.append(factor_id)

        for window in windows:
            name = perturbation_factor_name(factor_id, window)
            if window == int(base_window):
                # Still emit it: the gate asks for this name and has no fallback.
                values = base_values
            else:
                variant_expression, replacements = substitute_window(expression, int(base_window), window)
                if replacements == 0:
                    failures.append((factor_id, f"window {base_window} not found in the expression for variant {window}"))
                    continue
                if replacements > 1 and (factor_id, replacements) not in ambiguous:
                    ambiguous.append((factor_id, replacements))
                try:
                    values = pd.Series(compile_formula(variant_expression)(panel))
                except Exception as exc:  # noqa: BLE001
                    failures.append((factor_id, f"variant {window}: {type(exc).__name__}: {exc}"))
                    continue
            frames.append(pd.DataFrame({
                args.date_column: dates, args.code_column: codes,
                "factor_name": name, "value": values.to_numpy(dtype=float),
            }))

        if position % 50 == 0 or position == len(candidates):
            elapsed = time.perf_counter() - started
            rate = elapsed / position
            print(f"  {position}/{len(candidates)}  {rate:.2f}s/factor  "
                  f"eta {(len(candidates) - position) * rate / 60:.1f} min")

    if not frames:
        raise FactorValueError("nothing was computed; refusing to write an empty dataset")

    table = pd.concat(frames, ignore_index=True)
    table["value"] = pd.to_numeric(table["value"], errors="coerce")
    table = table.replace([np.inf, -np.inf], np.nan)
    table = table.sort_values([args.date_column, args.code_column, "factor_name"], kind="stable")

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()
    table.to_parquet(output, index=False)

    sidecar_path = Path(args.sidecar) if args.sidecar else Path(f"{output}.json")
    sidecar = {
        "source": f"scripts/build_factor_values.py from {Path(args.panel_file).name}",
        "dataset": DATASET,
        "data_start": str(dates.min().date()),
        "data_end": str(dates.max().date()),
        "row_count": int(len(table)),
        "sha256": sha256_file(output),
        "factors": factors_meta,
        "value_definition": VALUE_DEFINITION,
        "generated_at": datetime.now(CN_TZ).isoformat(timespec="seconds"),
        "candidates_file": str(args.candidates),
        "configuration_file": str(args.config),
        "multipliers": multipliers,
        "variant_rows": int(len(table) - sum(1 for _, group in table.groupby("factor_name", sort=False))),
    }
    sidecar_path.write_text(json.dumps(sidecar, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nwrote {output}")
    print(f"  rows       : {len(table):,}")
    print(f"  base factor: {len(factors_meta)}")
    print(f"  total series: {table['factor_name'].nunique():,}")
    print(f"  shared with: {sidecar_path}")

    if vacuous:
        print(f"\n⚠ {len(vacuous)} candidate(s) have a VACUOUS perturbation: every variant window")
        print("  equals the base, so the gate passes without the parameter ever moving.")
        print("  This is the frozen gate's own arithmetic and is reported, not hidden:")
        for factor_id in vacuous[:10]:
            print(f"    {factor_id}")
    if ambiguous:
        print(f"\n{len(ambiguous)} factor(s) had the window value appear more than once; "
              "all occurrences were substituted:")
        for factor_id, count in ambiguous[:10]:
            print(f"    {factor_id}: {count} occurrences")
    if failures:
        print(f"\n{len(failures)} failure(s):")
        for factor_id, reason in failures[:15]:
            print(f"    {factor_id}: {reason[:100]}")

    report = {
        "candidates": len(candidates),
        "base_factors": len(factors_meta),
        "series": int(table["factor_name"].nunique()),
        "rows": int(len(table)),
        "multipliers": multipliers,
        "vacuous_perturbation": vacuous,
        "ambiguous_window_substitutions": [{"factor_id": f, "occurrences": c} for f, c in ambiguous],
        "failures": [{"factor_id": f, "reason": r} for f, r in failures],
        "seconds": time.perf_counter() - started,
    }
    report_path = Path(args.report) if args.report else Path(f"{output}.report.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  report     : {report_path}")

    if failures:
        print("\nFAILURES PRESENT -- fix them before submitting; a missing factor is a "
              "silent not_run in the catalog.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
