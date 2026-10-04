"""What would it take to unlock the remaining unparsable / blocked catalog factors?

Read-only analysis. For each factor the classifier cannot handle, report whether
the blocker is (a) the ternary operator only, (b) a missing field only, or (c)
both, so the cheapest useful grammar or field extension can be chosen on evidence
rather than guesswork.
"""
from __future__ import annotations

import collections
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from research_core.factor_lab.catalog_readiness import classify_expression  # noqa: E402
from research_core.factor_lab.formula_compiler import (  # noqa: E402
    _OPERATOR_INDEX,
    _normalise_operator,
    resolve_operator_name,
)

CATALOG = ROOT / "pages" / "factor-db-dashboard" / "data" / "factors.json"
TERNARY = re.compile(r"\?[^:]*:")
FUNC_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(")
FIELD_RE = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)")

#: Fields the compiler can synthesise from the panel rather than requiring a column.
SYNTHESISABLE = {"returns", "daily_return", "vwap"}


def main() -> int:
    factors = json.loads(CATALOG.read_text(encoding="utf-8"))["factors"]

    unparsable_only_ternary = []
    unparsable_other = []
    blocked_ops = collections.Counter()
    blocked_fields = collections.Counter()

    for factor in factors:
        factor_id = factor["factor_id"]
        expression = factor["formula_expr"]
        verdict = classify_expression(expression)

        if verdict.verdict == "unparsable":
            stripped = TERNARY.sub("", expression)
            still_fails = False
            if "?" in stripped:
                still_fails = True
            if not still_fails:
                try:
                    from research_core.factor_lab.formula_compiler import Parser, tokenize

                    Parser(tokenize(stripped.replace("$", ""))).parse()
                except Exception:  # noqa: BLE001
                    still_fails = True
            if still_fails:
                unparsable_other.append((factor_id, verdict.parse_error or ""))
            else:
                unparsable_only_ternary.append((factor_id, expression))
        elif verdict.verdict == "needs_numerics":
            for name in verdict.unresolved_operators:
                blocked_ops[name] += 1
            for name in verdict.missing_fields:
                blocked_fields[name] += 1

    total = len(factors)
    print(f"catalog {total}")
    print(f"  unparsable, ONLY the ternary stands in the way : {len(unparsable_only_ternary)}")
    print(f"  unparsable for another reason                  : {len(unparsable_other)}")
    print()

    print("of the ternary-only group, which extra fields do they reference?")
    field_use = collections.Counter()
    for _factor_id, expression in unparsable_only_ternary:
        for name in set(FIELD_RE.findall(expression)):
            field_use[name.upper()] += 1
    print(f"  {'field':<14} {'factors':>8}  synthesiseable from the panel?")
    for name, count in field_use.most_common(12):
        flag = "yes" if name.lower() in SYNTHESISABLE else "NO -- needs an export/derivation"
        print(f"  {name:<14} {count:>8}  {flag}")

    print()
    print("of the ternary-only group, which functions do they call?")
    funcs = collections.Counter()
    for _factor_id, expression in unparsable_only_ternary:
        for name in set(FUNC_RE.findall(expression)):
            funcs[name.upper()] += 1
    for name, count in funcs.most_common(12):
        known = resolve_operator_name(name) in _OPERATOR_INDEX.values()
        print(f"  {name:<16} x{count:<4} {'ok' if known else 'NOT IMPLEMENTED'}")

    print()
    print("remaining operator blockers (needs_numerics group):")
    for name, count in blocked_ops.most_common(15):
        print(f"  {name:<18} blocks x{count}")
    print()
    print("remaining field blockers (needs_numerics group):")
    for name, count in blocked_fields.most_common(15):
        print(f"  {name:<18} blocks x{count}")

    print()
    print(f"summary: ternary support alone would recover {len(unparsable_only_ternary)} "
          f"factors ({len(unparsable_only_ternary) / total:.1%} of the catalog) "
          "before any field work.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
