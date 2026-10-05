"""Build the candidate list for the 300-factor target from the factor catalog.

The frozen `candidate_list.csv` holds 91 candidates. The delivery target is 300.
**At a 100% pass rate, 91 candidates yield 81 effective alpha -- the arithmetic
cannot close.** Whatever the gates do, the candidate pool has to be widened, and
that is a scoping decision that follows from the target rather than from any
change to the frozen thresholds.

This emits a candidate list from the 961 catalog factors the engine can actually
compute, with the metadata the delivery catalog needs, and refuses to include
anything it cannot compute.

Two exclusions are automatic, because they follow from rulings already made:

* **Risk exposures are marked, not dropped.** BARRA and JQGM entries are style or
  risk factors. The ruling is that they still run and report a status but never
  count as effective alpha and never enter the package, so they are flagged
  `risk_exposure=true` and left to the accounting rather than silently removed.
* **Factors the engine cannot compute are omitted**, because a candidate that
  cannot be evaluated produces a `not_run` row at best.

    python -X utf8 scripts/build_candidate_list.py --out data/factor_lab/candidate_list.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research_core.factor_lab.catalog_readiness import classify_expression  # noqa: E402
from research_core.factor_lab.formula_compiler import (  # noqa: E402
    _GENERIC_OPERATORS,
    _PANEL_OPERATORS,
    _WIDE_OPERATORS,
    Parser,
    tokenize,
)

CATALOG = ROOT / "pages" / "factor-db-dashboard" / "data" / "factors.json"

#: Columns the batch validator requires plus the metadata the delivery catalog
#: reads. `factor_id` is required; `risk_exposure` and `window` change how a
#: factor is treated; the rest is provenance.
COLUMNS = (
    "factor_id",
    "name",
    "formula",
    "category",
    "required_fields",
    "direction",
    "risk_exposure",
    "window",
)

#: Families that are risk or style exposures rather than alpha. The ruling is that
#: they run but never count as effective alpha.
RISK_FAMILIES = {"BARRA", "JQGM"}

#: Operators whose trailing argument is a window length.
WINDOW_OPERATORS = frozenset(_PANEL_OPERATORS) | frozenset(_WIDE_OPERATORS) | {"REF", "DELAY"}


def _collect_calls(node, out: list) -> None:  # noqa: ANN001
    from research_core.factor_lab.formula_compiler import BinOp, FuncCall, IfExpr, UnaryOp

    if isinstance(node, FuncCall):
        out.append(node)
        for arg in node.args:
            _collect_calls(arg, out)
    elif isinstance(node, BinOp):
        _collect_calls(node.left, out)
        _collect_calls(node.right, out)
    elif isinstance(node, UnaryOp):
        _collect_calls(node.operand, out)
    elif isinstance(node, IfExpr):
        _collect_calls(node.cond, out)
        _collect_calls(node.true_val, out)
        _collect_calls(node.false_val, out)


def primary_window(expression: str) -> int | None:
    """The window length to perturb, or None when the expression has no window.

    Convention: among the integer literals passed as the trailing argument of a
    window-taking operator, take the most frequent one; ties go to the smallest.
    That is what the factor's own formula treats as its parameter, and it is
    stated here because the perturbation gate depends on it.

    An expression with no such literal has no measurable window. Per the frozen
    ruling that means `parameter_perturbation` is recorded as unmeasurable and
    NOT passed -- which is why the count of windowless candidates matters and is
    reported rather than hidden.
    """
    from research_core.factor_lab.formula_compiler import Literal

    try:
        ast = Parser(tokenize(expression)).parse()
    except Exception:  # noqa: BLE001
        return None

    calls: list = []
    _collect_calls(ast, calls)

    candidates: Counter[int] = Counter()
    for call in calls:
        name = call.func.upper().replace("_", "")
        if name not in {op.replace("_", "") for op in WINDOW_OPERATORS}:
            continue
        for argument in reversed(call.args):
            if isinstance(argument, Literal) and float(argument.value).is_integer():
                value = int(argument.value)
                if 2 <= value <= 500:
                    candidates[value] += 1
                break

    if not candidates:
        return None
    best = max(candidates.values())
    return min(value for value, count in candidates.items() if count == best)


def build_rows(
    factors: list[dict], *, include_not_runnable: bool, include_windowless: bool = False
) -> tuple[list[dict], dict]:
    rows: list[dict] = []
    stats: Counter = Counter()
    # Seed the counters a reader will look for, so a caller never has to guess
    # whether a missing key means "zero" or "not measured".
    stats["with_window"] = 0
    stats["without_window"] = 0
    stats["risk_exposure"] = 0
    stats["skipped_not_runnable"] = 0
    stats["skipped_windowless"] = 0
    skipped: list[tuple[str, str]] = []

    for factor in factors:
        factor_id = factor["factor_id"]
        family = factor_id.split(":")[0]
        expression = factor.get("formula_expr", "")
        verdict = classify_expression(expression)

        if not verdict.runnable and not include_not_runnable:
            stats["skipped_not_runnable"] += 1
            skipped.append((factor_id, verdict.verdict + (f": {verdict.unresolved_operators}" if verdict.unresolved_operators else "")))
            continue

        window = primary_window(expression)
        if window is None and not include_windowless:
            # Structural, not a threshold: the factor file's sidecar requires a
            # positive integer window for every declared factor, so a windowless
            # candidate cannot be represented, cannot be given a base window by
            # the validator, and cannot be delivered. Leaving it in the candidate
            # list would make validate-batch error on a factor missing from the
            # factor file, or fail its perturbation gate as unmeasured.
            stats["skipped_windowless"] += 1
            skipped.append((factor_id, "no window: cannot be declared in the factor file (see Q11)"))
            continue

        stats["with_window" if window else "without_window"] += 1
        if family in RISK_FAMILIES:
            stats["risk_exposure"] += 1

        rows.append(
            {
                "factor_id": factor_id,
                "name": factor.get("name_cn") or "",
                "formula": expression,
                "category": factor.get("category") or "",
                "required_fields": ";".join(verdict.fields_used),
                "direction": "",
                "risk_exposure": "true" if family in RISK_FAMILIES else "false",
                "window": "" if window is None else str(window),
            }
        )

    return rows, {"stats": dict(stats), "skipped": skipped}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--catalog", default=str(CATALOG))
    parser.add_argument("--out", default="data/factor_lab/candidate_list.csv")
    parser.add_argument("--families", default="", help="comma-separated source families to include")
    parser.add_argument(
        "--include-not-runnable",
        action="store_true",
        help="emit factors the engine cannot compute; they will only ever be not_run",
    )
    parser.add_argument(
        "--include-windowless",
        action="store_true",
        help="emit windowless factors, which the factor file cannot declare and therefore cannot deliver",
    )
    args = parser.parse_args(argv)

    factors = json.loads(Path(args.catalog).read_text(encoding="utf-8"))["factors"]
    wanted = {name.strip().upper() for name in args.families.split(",") if name.strip()}
    if wanted:
        factors = [f for f in factors if f["factor_id"].split(":")[0].upper() in wanted]

    rows, report = build_rows(
        factors,
        include_not_runnable=args.include_not_runnable,
        include_windowless=args.include_windowless,
    )

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(COLUMNS))
        writer.writeheader()
        writer.writerows(rows)

    stats = report["stats"]
    candidates = len(rows)
    alpha = sum(1 for row in rows if row["risk_exposure"] == "false")
    windowed = stats.get("with_window", 0)

    print(f"wrote {out}")
    print(f"  candidates          : {candidates}")
    print(f"  countable as alpha  : {alpha}   (risk exposures: {stats.get('risk_exposure', 0)})")
    print(f"  with a window       : {windowed}")
    print(f"  excluded, windowless: {stats.get('skipped_windowless', 0)}  "
          "(the factor file cannot declare them; see Q11)")
    print(f"  excluded, uncomputable: {stats.get('skipped_not_runnable', 0)}")
    print()
    print("THE ARITHMETIC THAT MATTERS")
    print(f"  a 100% pass rate over {alpha} countable candidates yields at most {alpha} factors")
    for rate in (0.20, 0.30, 0.40, 0.50):
        projected = int(alpha * rate)
        verdict = "OK" if projected >= 300 else f"SHORT by {300 - projected}"
        print(f"    at a {rate:.0%} pass rate -> {projected:>4} factors   {verdict}")
    print()
    print("  The frozen 91-candidate scope cannot reach 300 at any pass rate;")
    print("  widening the candidate pool is a scoping decision, not a threshold change.")

    if stats.get("skipped_not_runnable"):
        print()
        print("  first few uncomputable:")
        for factor_id, reason in [s for s in report["skipped"] if "no window" not in s[1]][:5]:
            print(f"    {factor_id}: {reason[:80]}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
