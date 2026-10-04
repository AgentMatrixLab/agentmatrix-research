"""Report the honest readiness split, including the field-aware verdict."""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from research_core.factor_lab.catalog_readiness import classify_expression  # noqa: E402

CATALOG = ROOT / "pages" / "factor-db-dashboard" / "data" / "factors.json"


def main() -> int:
    factors = json.loads(CATALOG.read_text(encoding="utf-8"))["factors"]
    verdicts: collections.Counter = collections.Counter()
    fields: collections.Counter = collections.Counter()
    by_source: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)

    for factor in factors:
        verdict = classify_expression(factor["formula_expr"])
        verdicts[verdict.verdict] += 1
        by_source[factor["factor_id"].split(":")[0]][verdict.verdict] += 1
        if verdict.verdict == "needs_fields":
            for name in verdict.missing_fields:
                fields[name] += 1

    total = len(factors)
    runnable = verdicts["runnable_now"] + verdicts["alias_only"]
    print(f"catalog: {total}")
    for verdict, count in verdicts.most_common():
        print(f"  {verdict:<16} {count:>5}  {count / total:>6.1%}")
    print(f"\nhonest runnable: {runnable}/{total} = {runnable / total:.1%}")
    print()
    print("by source:")
    for source in sorted(by_source):
        row = by_source[source]
        run = row["runnable_now"] + row["alias_only"]
        total_source = sum(row.values())
        print(f"  {source:<10} runnable {run:>4}/{total_source:<4}  needs_fields {row['needs_fields']:>3}")
    print()
    print("fields blocking otherwise-runnable factors:")
    for name, count in fields.most_common(15):
        print(f"  {name:<16} x{count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
