"""Inspect how the catalog uses the operators that are currently blocking it.

Read-only. Prints, per blocking operator, the distinct call shapes observed so
the implementations can be written against real usage rather than guessed.
"""
from __future__ import annotations

import collections
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from research_core.factor_lab.catalog_readiness import (  # noqa: E402
    classify_expression,
    readiness_summary,
)

CATALOG = ROOT / "pages" / "factor-db-dashboard" / "data" / "factors.json"
CALL_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(([^()]*(?:\([^()]*\)[^()]*)*)\)")


def main() -> int:
    factors = json.loads(CATALOG.read_text(encoding="utf-8"))["factors"]
    summary = readiness_summary(classify_expression(f["formula_expr"]) for f in factors)

    blockers = list(summary["operator_blockers"].items())
    print(f"blocking operators: {len(blockers)}, blocked expressions: {sum(c for _, c in blockers)}")
    print()

    counts: collections.Counter[str] = collections.Counter()
    shapes: dict[str, collections.Counter[str]] = collections.defaultdict(collections.Counter)

    for f in factors:
        verdict = classify_expression(f["formula_expr"])
        if not verdict.unresolved_operators:
            continue
        expr = f["formula_expr"].replace("$", "")
        for name, args in CALL_RE.findall(expr):
            upper = name.upper()
            if upper in verdict.unresolved_operators:
                shapes[upper][args.strip()[:70]] += 1
                counts[upper] += 1

    for name, total in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"{name}  (blocks {summary['operator_blockers'][name]} expressions, {total} call sites)")
        for args, n in shapes[name].most_common(4):
            print(f"    x{n:<3} ({args})")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
