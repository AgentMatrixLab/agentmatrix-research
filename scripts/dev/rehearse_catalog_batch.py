"""Rehearse the frozen batch validator against REAL catalog candidates.

`rehearse_full_pipeline.py` proves the chain is wired, but it drives it with a
dozen hand-written `REH_*` expressions. The list that will actually be submitted
is `scripts/build_candidate_list.py`'s output: 961 catalog factors, each with a
window inferred by convention and perturbation variants derived from it. None of
that has ever met the frozen validator.

That gap matters because the perturbation gate asks the factor file for
`<id>|window=<round(base * multiplier)>`. If the inferred base window disagrees
with what the pipeline derives, the variant is missing, the gate records
"unmeasurable", and the factor is rejected -- silently, and identically for every
affected factor. Better to find that here than on 10/6.

    python -X utf8 scripts/dev/rehearse_catalog_batch.py --factors 40
"""

from __future__ import annotations

import argparse
import csv as _csv
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "dev"))

import build_candidate_list as candidate_builder  # noqa: E402
import rehearse_full_pipeline as rehearsal  # noqa: E402
from research_core.factor_lab.catalog_readiness import classify_expression  # noqa: E402
from research_core.factor_lab.formula_compiler import compile_formula  # noqa: E402

CATALOG = ROOT / "pages" / "factor-db-dashboard" / "data" / "factors.json"
VARIANT_MARKER = "|window="


def substitute_window(expression: str, old: int, new: int) -> str:
    return re.sub(rf"(?<![0-9.]){old}(?![0-9.])", str(new), expression, count=1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--factors", type=int, default=40)
    parser.add_argument("--codes", type=int, default=40)
    parser.add_argument("--seed", type=int, default=20261005)
    parser.add_argument("--work-dir", default=".tmp-catalog-batch")
    parser.add_argument(
        "--families",
        default="ALPHA158,ALPHA360,GTJA191,ALPHA101",
        help="which source families to draw candidates from",
    )
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args(argv)

    work = ROOT / args.work_dir
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []

    print("=== 1/5 synthetic panel ===")
    rehearsal.N_CODES = args.codes
    panel = rehearsal.build_panel(args.seed)
    panel_path = rehearsal.write_panel(panel, work)
    print(f"  {len(panel):,} rows, {panel['code'].nunique()} codes")

    print("\n=== 2/5 real catalog candidates ===")
    factors = json.loads(CATALOG.read_text(encoding="utf-8"))["factors"]
    wanted = {name.strip().upper() for name in args.families.split(",") if name.strip()}
    rows, report = candidate_builder.build_rows(factors, include_not_runnable=False)
    rows = [row for row in rows if row["factor_id"].split(":")[0] in wanted and row["window"]]
    print(f"  {len(rows)} windowed candidates available across {sorted(wanted)}")
    if not rows:
        raise SystemExit("no candidates with windows in the requested families")
    # Spread across families rather than taking a block, so the sample is not all
    # one library.
    by_family: dict[str, list[dict]] = {}
    for row in rows:
        by_family.setdefault(row["factor_id"].split(":")[0], []).append(row)
    selected: list[dict] = []
    index = 0
    while len(selected) < args.factors and any(by_family.values()):
        for family in sorted(by_family):
            pool = by_family[family]
            if index < len(pool) and len(selected) < args.factors:
                selected.append(pool[index])
        index += 1
    print(f"  selected {len(selected)}: "
          + ", ".join(f"{f}={sum(1 for s in selected if s['factor_id'].startswith(f))}"
                      for f in sorted(by_family)))

    print("\n=== 3/5 production candidate + factor-value build ===")
    # Drive the real scripts, not a parallel implementation. An earlier version of
    # this rehearsal built the factor table itself, which is how the absence of a
    # production builder went unnoticed.
    wanted_ids = {row["factor_id"] for row in selected}
    candidate_rows = [row for row in rows if row["factor_id"] in wanted_ids]
    candidates_path = work / "candidate_list.csv"
    with candidates_path.open("w", encoding="utf-8", newline="") as handle:
        writer = _csv.DictWriter(handle, fieldnames=list(candidate_builder.COLUMNS))
        writer.writeheader()
        writer.writerows(candidate_rows)
    print(f"  candidate list: {len(candidate_rows)} rows")

    factor_path = work / "factor_values.parquet"
    builder = subprocess.run(
        [sys.executable, "-X", "utf8", str(ROOT / "scripts" / "build_factor_values.py"),
         "--candidates", str(candidates_path),
         "--panel-file", str(panel_path),
         "--config", str(ROOT / "configs" / "validation_gates.yaml"),
         "--output", str(factor_path),
         "--report", str(work / "factor_values_report.json")],
        cwd=ROOT, capture_output=True, text=True,
    )
    for line in (builder.stdout or "").strip().splitlines()[-12:]:
        print(f"  {line}")
    if builder.returncode != 0:
        print("  build_factor_values FAILED")
        for line in (builder.stderr or "").strip().splitlines()[-15:]:
            print(f"    {line}")
        return 1
    computed = sorted(candidate_rows, key=lambda row: row["factor_id"])
    declared = {row["factor_id"]: {"window": int(row["window"])} for row in computed}

    print("\n=== 4/5 frozen validate-batch ===")
    config_path = rehearsal.write_rehearsal_config(work)
    command = [
        sys.executable, "-X", "utf8", "-m", "research_core.factor_lab.cli", "validate-batch",
        "--candidates", str(candidates_path),
        "--config", str(config_path),
        "--panel-file", str(panel_path),
        "--factor-file", str(factor_path),
        "--segment", "oos",
        "--output-dir", str(work / "batch"),
    ]
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    if completed.returncode != 0:
        print(f"  validate-batch FAILED (exit {completed.returncode})")
        print("  --- stdout tail ---")
        for line in (completed.stdout or "").strip().splitlines()[-25:]:
            print(f"    {line}")
        print("  --- stderr tail ---")
        for line in (completed.stderr or "").strip().splitlines()[-25:]:
            print(f"    {line}")
        if args.keep:
            print(f"  artefacts in {work}")
        return 1

    runs_dir = work / "validation_runs"
    results = []
    for path in sorted(runs_dir.glob("*/validation_result.json")):
        results.append(json.loads(path.read_text(encoding="utf-8")))

    # `needs_human` is a legitimate outcome, not a failure: the pipeline writes it
    # when a factor cannot be judged (here, a ternary whose condition never fires
    # on this panel, leaving no RankIC observations). Counting it as a missing
    # result would push a correct refusal into the failure column.
    needs_human = []
    for path in sorted(runs_dir.glob("*/needs_human.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        needs_human.append((payload.get("factor_id", path.parent.name), payload.get("reason", "")))

    print(f"  {len(results)} results + {len(needs_human)} needs_human, "
          f"for {len(computed)} computed factors")
    if len(results) + len(needs_human) != len(computed):
        failures.append(
            f"{len(computed) - len(results) - len(needs_human)} factor(s) produced neither "
            "a result nor a needs_human record"
        )
    for factor_id, reason in needs_human[:5]:
        print(f"    needs_human {factor_id}: {reason[:80]}")

    validated = [r for r in results if not r.get("failed_gates")]
    print(f"  passed every gate: {len(validated)}/{len(results)}")

    # The specific thing this rehearsal exists to catch.
    unmeasured = [
        r["factor_id"] for r in results
        if any(
            g.get("name") == "parameter_perturbation"
            and isinstance(g.get("actual"), dict)
            and g["actual"].get("measured") is False
            for g in r.get("gates", [])
        )
    ]
    print(f"\n  perturbation UNMEASURABLE: {len(unmeasured)}/{len(results)}")
    if unmeasured:
        print("    the variant windows we wrote did not match what the gate asked for:")
        for factor_id in unmeasured[:10]:
            print(f"      {factor_id}")
        failures.append(
            f"{len(unmeasured)} factor(s) had an unmeasurable perturbation gate despite "
            "carrying variants -- the declared base window disagrees with the gate's derivation"
        )
    else:
        print("    every windowed candidate had a measurable perturbation variant")

    reasons: dict[str, int] = {}
    for result in results:
        key = ",".join(result.get("failed_gates") or []) or "validated"
        reasons[key] = reasons.get(key, 0) + 1
    print("\n  outcomes:")
    for key, count in sorted(reasons.items(), key=lambda kv: -kv[1]):
        print(f"    x{count:<4} {key}")

    print("\n" + "=" * 64)
    if failures:
        print("CATALOG BATCH REHEARSAL FAILED")
        for item in failures:
            print(f"  - {item}")
    else:
        print("CATALOG BATCH REHEARSAL PASSED")
    print("SYNTHETIC PANEL, REAL CATALOG EXPRESSIONS -- not evidence about any factor.")

    if not args.keep and not failures:
        shutil.rmtree(work, ignore_errors=True)
    else:
        print(f"artefacts kept in {work}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
