"""Inspect what still fails to parse after ternary support was added."""
from __future__ import annotations

import collections
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from research_core.factor_lab.catalog_readiness import classify_expression  # noqa: E402

CATALOG = ROOT / "pages" / "factor-db-dashboard" / "data" / "factors.json"


def main() -> int:
    factors = json.loads(CATALOG.read_text(encoding="utf-8"))["factors"]
    bad = [f for f in factors if classify_expression(f["formula_expr"]).verdict == "unparsable"]

    print(f"unparsable after ternary support: {len(bad)}")
    print()
    buckets: collections.Counter = collections.Counter()
    samples: dict[str, str] = {}
    for factor in bad:
        verdict = classify_expression(factor["formula_expr"])
        error = verdict.parse_error or ""
        match = re.search(r"Unexpected token at position \d+: '(.{0,20})", error)
        token = match.group(1) if match else error[:20]
        family = factor["factor_id"].split(":")[0]
        buckets[(family, token)] += 1
        samples.setdefault((family, token), factor["factor_id"] + " :: " + factor["formula_expr"][:150])

    for key, count in buckets.most_common(15):
        print(f"  x{count:<3} [{key[0]}] token {key[1]!r}")
        print(f"        {samples[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
