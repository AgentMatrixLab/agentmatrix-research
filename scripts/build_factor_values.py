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
import pyarrow as pa
import pyarrow.parquet as pq
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


def _series_arrow_schema() -> "pa.Schema":
    """The four columns the factor_values dataset is defined to carry."""
    return pa.schema([
        pa.field("date", pa.timestamp("ns")),
        pa.field("code", pa.string()),
        pa.field("factor_name", pa.string()),
        pa.field("value", pa.float64()),
    ])


def _fields_used(expressions: list[str]) -> set[str]:
    from research_core.factor_lab.catalog_readiness import classify_expression

    names: set[str] = set()
    for expression in expressions:
        try:
            names.update(classify_expression(expression).fields_used)
        except Exception:  # noqa: BLE001
            continue
    return names


def required_panel_columns(expressions: list[str], available: list[str]) -> list[str]:
    """The panel columns this shard's expressions actually read, plus the keys.

    Measured on the real 9.44M-row panel a single worker held 14.9 GB, because
    every `df.assign(...)` in the generated code copies the whole frame and so
    copies every unused column with it. Loading only what the shard needs cuts
    both the resident size and the cost of those copies.

    `date` and `code` are always kept. Anything still missing surfaces later as a
    KeyError with a real message, which is the behaviour the computability guard
    already pins.
    """
    from research_core.factor_lab.formula_compiler import DEFAULT_FIELD_MAP

    present = set(available)
    keep = {"date", "code"}
    fields = _fields_used(expressions)
    for field in fields:
        column = DEFAULT_FIELD_MAP.get(field.upper(), field.lower())
        if column in present:
            keep.add(column)
    # Fields the generator builds itself: the columns they derive from never
    # appear as a field name in the expression.
    if any(name.startswith("ADV") for name in fields):
        if "total_turnover" in present:
            keep.add("total_turnover")
        keep.add("volume")
    if any(name in ("RETURNS", "DAILY_RETURN") for name in fields):
        keep.add("close")
    # indneutralize reads the industry column even when the expression reaches it
    # through IndClass.sector, which the classifier reports under its own name.
    if any("indneutralize" in expression.lower() for expression in expressions):
        keep.add("industry")
    return sorted(keep & present)


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


#: Worker state for the parallel build path. The panel is installed once per process by fork,
#: so it is shared rather than pickled with every task.
_BUILD_WORKER: dict = {}


def _init_build_worker(panel: pd.DataFrame, candidates: list, multipliers: list[float]) -> None:
    _BUILD_WORKER.clear()
    _BUILD_WORKER["panel"] = panel
    _BUILD_WORKER["candidates"] = candidates
    _BUILD_WORKER["multipliers"] = multipliers


def compute_one_candidate(index: int) -> dict:
    """Compute one candidate's base series and its perturbation variants.

    Returns the values rather than writing them, so the caller can emit in the original order.
    Extraction is what makes the build parallelisable: the phases are independent per candidate
    and the box is CPU-idle, while the shard's other phases are memory-bound and cannot be
    spread. Everything here mirrors the serial path exactly, including which failures are
    recorded and in what order the series are produced.
    """
    panel = _BUILD_WORKER["panel"]
    candidate = _BUILD_WORKER["candidates"][index]
    multipliers = _BUILD_WORKER["multipliers"]

    factor_id = candidate.factor_id
    metadata = candidate.metadata or {}
    expression = metadata.get("formula", "")
    if not expression:
        return {"factor_id": factor_id, "failure": "candidate carries no formula"}

    base_window = candidate.window
    if base_window is None:
        # Not merely at risk: the sidecar contract requires every declared factor to carry a
        # positive integer window, so a windowless factor cannot be represented in this file at
        # all, and the validator cannot obtain a base window for it. Excluding it here is the
        # honest outcome.
        return {
            "factor_id": factor_id,
            "failure": "no window: the factor file cannot declare a windowless factor, "
                       "so this candidate cannot be validated (see Q11)",
        }

    try:
        base_values = pd.Series(compile_formula(expression)(panel))
    except UnsupportedOperatorError as exc:
        return {"factor_id": factor_id, "failure": f"unsupported operator: {exc}"}
    except Exception as exc:  # noqa: BLE001
        return {"factor_id": factor_id, "failure": f"{type(exc).__name__}: {exc}"}

    emitted: list[tuple[str, pd.Series]] = [(factor_id, base_values)]
    failures: list[str] = []
    ambiguous: int | None = None
    windows = variant_windows(int(base_window), multipliers)
    for window in windows:
        name = perturbation_factor_name(factor_id, window)
        if window == int(base_window):
            # Still emit it: the gate asks for this name and has no fallback.
            values = base_values
        else:
            variant_expression, replacements = substitute_window(
                expression, int(base_window), window
            )
            if replacements == 0:
                failures.append(
                    f"window {base_window} not found in the expression for variant {window}"
                )
                continue
            if replacements > 1:
                ambiguous = replacements
            try:
                values = pd.Series(compile_formula(variant_expression)(panel))
            except Exception as exc:  # noqa: BLE001
                failures.append(f"variant {window}: {type(exc).__name__}: {exc}")
                continue
        emitted.append((name, values))

    return {
        "factor_id": factor_id,
        "window": int(base_window),
        "emitted": emitted,
        "vacuous": all(window == int(base_window) for window in windows),
        "ambiguous": ambiguous,
        "failures": failures,
    }


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
    parser.add_argument(
        "--emit-start",
        default="",
        help="only store rows on or after this date; earlier rows are computed "
             "for warm-up but never written",
    )
    parser.add_argument("--report", default="", help="where to write the build report JSON")
    parser.add_argument(
        "--jobs",
        type=int,
        default=1,
        help="processes for the per-candidate maths. The build is single-threaded and the box "
             "is CPU-idle while the shard's train/oos phases are memory-bound and cannot be "
             "spread, so this is the one phase that can use spare cores. Measured builds span "
             "140 s to 1851 s depending on formula nesting, and for the expensive ones the "
             "build is most of the shard. Series are still emitted in the original order, so "
             "the file is byte-identical; fork shares the panel. Ignored where fork is "
             "unavailable.",
    )
    args = parser.parse_args(argv)

    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    multipliers = [float(m) for m in config["perturbation"]["multipliers"]]
    candidates = load_candidate_list(args.candidates)
    if args.limit:
        candidates = candidates[: args.limit]
    print(f"candidates: {len(candidates)}   multipliers: {multipliers}")

    # Column names come from the Parquet schema, not from the data. `pd.read_parquet(...)
    # .columns` reads the entire 817 MB panel to produce a list of names, and this runs in
    # every shard's build phase -- an hour of pure waste across 213 shards, plus a multi-GB
    # spike for nothing.
    schema_columns = list(pq.ParquetFile(args.panel_file).schema_arrow.names)
    expressions = [(c.metadata or {}).get("formula", "") for c in candidates]
    keep_columns = required_panel_columns(expressions, schema_columns)
    print(f"panel columns kept: {len(keep_columns)}/{len(schema_columns)} -> {keep_columns}")

    panel = pd.read_parquet(args.panel_file, columns=keep_columns)
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

    factors_meta: dict[str, dict] = {}
    failures: list[tuple[str, str]] = []
    vacuous: list[str] = []
    ambiguous: list[tuple[str, int]] = []
    started = time.perf_counter()

    # Write each series as soon as it is computed and release it, rather than
    # accumulating the shard and writing at the end. Holding a 53-factor shard's
    # series costs about 12 GB (159 series x 9.44M values x 8 bytes), which capped
    # the run at four workers and left it within a few GB of the OOM killer.
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()
    writer = pq.ParquetWriter(output, schema=_series_arrow_schema(), compression="zstd")
    series_count = 0
    total_rows = 0
    emitted_start = None
    emitted_end = None

    # Rows before the frozen train start are warm-up: needed to compute the values,
    # never read by the validator, and expensive to carry in a file that has to be
    # loaded whole.
    if args.emit_start:
        emit_mask = (dates >= pd.Timestamp(args.emit_start)).to_numpy()
        print(f"emit filter: keeping rows on/after {args.emit_start} "
              f"({int(emit_mask.sum()):,}/{len(emit_mask):,} = {emit_mask.mean():.1%})", flush=True)
    else:
        emit_mask = None

    def emit(name: str, values: pd.Series) -> None:
        """Write one factor series and release it immediately.

        Only rows inside the frozen split are written. The panel starts in 2018
        for warm-up, but the validator never looks before train_start, and those
        extra rows are not free: they inflate the file the validator has to load
        whole, which is what pushed a 158-series shard to 48 GB and got it killed
        by the OOM killer.
        """
        nonlocal series_count, total_rows, emitted_start, emitted_end
        series = pd.to_numeric(pd.Series(values), errors="coerce").to_numpy(dtype=float)
        frame = pd.DataFrame({
            args.date_column: dates,
            args.code_column: codes,
            "factor_name": name,
            "value": series,
        })
        if emit_mask is not None:
            frame = frame[emit_mask]
        frame = frame.replace([np.inf, -np.inf], np.nan)
        writer.write_table(
            pa.Table.from_pandas(frame, schema=_series_arrow_schema(), preserve_index=False)
        )
        series_count += 1
        total_rows += len(frame)
        if len(frame):
            block_start = frame[args.date_column].min()
            block_end = frame[args.date_column].max()
            emitted_start = block_start if emitted_start is None else min(emitted_start, block_start)
            emitted_end = block_end if emitted_end is None else max(emitted_end, block_end)

    def apply(result: dict) -> None:
        """Record and emit one candidate's outcome, in the original order."""
        factor_id = result["factor_id"]
        if "emitted" not in result:
            failures.append((factor_id, result["failure"]))
            return
        for reason in result["failures"]:
            failures.append((factor_id, reason))
        factors_meta[factor_id] = {"window": result["window"]}
        if result["vacuous"]:
            vacuous.append(factor_id)
        replacements = result["ambiguous"]
        if replacements is not None and (factor_id, replacements) not in ambiguous:
            ambiguous.append((factor_id, replacements))
        for name, values in result["emitted"]:
            emit(name, values)

    # Installed in the parent too, so the serial path uses exactly the same code as the
    # workers. The pool's initializer re-installs it per worker process.
    _init_build_worker(panel, candidates, multipliers)

    pool = None
    context = None
    if args.jobs and args.jobs > 1:
        import multiprocessing

        if "fork" not in multiprocessing.get_all_start_methods():
            print("  --jobs ignored: the parallel build needs fork, which this platform lacks")
        else:
            context = multiprocessing.get_context("fork")
            pool = context.Pool(
                args.jobs,
                initializer=_init_build_worker,
                initargs=(panel, candidates, multipliers),
            )

    if pool is not None:
        print(f"  building with {args.jobs} process(es); series are still emitted in order")
        try:
            # imap preserves submission order, so results are emitted exactly as the serial
            # path would emit them and the written file is unchanged.
            for position, result in enumerate(
                pool.imap(compute_one_candidate, range(len(candidates)), chunksize=1), start=1
            ):
                apply(result)
                if position % 25 == 0 or position == len(candidates):
                    elapsed = time.perf_counter() - started
                    rate = elapsed / position
                    print(f"  {position}/{len(candidates)}  {rate:.2f}s/factor  "
                          f"eta {(len(candidates) - position) * rate / 60:.1f} min", flush=True)
        finally:
            pool.close()
            pool.join()
    else:
        for position, candidate in enumerate(candidates, start=1):
            apply(compute_one_candidate(position - 1))
            if position % 25 == 0 or position == len(candidates):
                elapsed = time.perf_counter() - started
                rate = elapsed / position
                print(f"  {position}/{len(candidates)}  {rate:.2f}s/factor  "
                      f"eta {(len(candidates) - position) * rate / 60:.1f} min", flush=True)

    writer.close()
    if series_count == 0:
        raise FactorValueError("nothing was computed; refusing to write an empty dataset")

    sidecar_path = Path(args.sidecar) if args.sidecar else Path(f"{output}.json")
    sidecar = {
        "source": f"scripts/build_factor_values.py from {Path(args.panel_file).name}",
        "dataset": DATASET,
        "data_start": str((emitted_start or dates.min()).date()),
        "data_end": str((emitted_end or dates.max()).date()),
        "row_count": int(total_rows),
        "sha256": sha256_file(output),
        "factors": factors_meta,
        "value_definition": VALUE_DEFINITION,
        "generated_at": datetime.now(CN_TZ).isoformat(timespec="seconds"),
        "candidates_file": str(args.candidates),
        "configuration_file": str(args.config),
        "multipliers": multipliers,
        "panel_columns_used": keep_columns,
    }
    sidecar_path.write_text(json.dumps(sidecar, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nwrote {output}")
    print(f"  rows       : {total_rows:,}")
    print(f"  base factor: {len(factors_meta)}")
    print(f"  series     : {series_count:,}")
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
        "series": series_count,
        "rows": int(total_rows),
        "multipliers": multipliers,
        "panel_columns_used": keep_columns,
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
