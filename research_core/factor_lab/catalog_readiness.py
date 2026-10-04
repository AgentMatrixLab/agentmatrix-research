"""Catalog readiness: can we actually compute a catalogued factor, and with what?

The Factor DB catalog (`pages/factor-db-dashboard/data/factors.json`) ships 1058
factor definitions written in Qlib/WorldQuant expression syntax. Before any of
them can enter the validation pipeline we must know, per factor, whether the
repository's own expression engine can evaluate it.

This module classifies each expression mechanically. It deliberately holds **no
operator table of its own**: the authority is `formula_compiler`, so the
classifier cannot drift away from what the engine can really execute.

Verdicts
--------
``runnable_now``
    Parses and every function call resolves to an operator already registered,
    and every field it references is one the panel can actually supply.
``alias_only``
    Same, except some calls use a verified synonym of a registered operator
    (``Ref`` for ``ts_delay``, ``Correlation`` for ``rolling_corr``, ...).
    Resolvable by the spelling table alone; no new numerics required.
``needs_numerics``
    At least one call names an operator with no implementation and no verified
    synonym.
``needs_fields``
    Every operator resolves, but the expression reads a field the panel cannot
    supply (``adv20``, ``returns``, ...). Counting these as runnable would
    overstate the candidate pool: the compiler would emit ``df["adv20"]`` and
    raise at call time, which is the same silent-overstatement defect the
    operator check exists to prevent.
``unparsable``
    The expression does not parse at all.

Read-only: this module never writes to disk and never touches the network.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import formula_compiler as fc

__all__ = [
    "ALIAS_MAP",
    "SUPPORTED_OPERATORS",
    "PANEL_FIELDS",
    "DERIVED_FIELDS",
    "RQDATA_ONLY_FIELDS",
    "FactorReadiness",
    "classify_expression",
    "readiness_summary",
]

# ── Operator vocabulary (derived from the engine, never restated) ───────

#: Operators the engine implements today.
SUPPORTED_OPERATORS: frozenset[str] = frozenset(
    set(fc._PANEL_OPERATORS)
    | set(fc._SERIES_OPERATORS)
    | set(fc._WIDE_OPERATORS)
    | set(fc._GENERIC_OPERATORS)
)

#: Verified spelling synonyms, normalised spelling -> canonical registry key.
ALIAS_MAP: dict[str, str] = dict(fc._OPERATOR_ALIASES)


def normalise_operator(name: str) -> str:
    """Fold case and underscores, matching the engine's own resolution rule."""
    return fc._normalise_operator(name)


def resolve_operator(name: str) -> str:
    """Resolve a catalog spelling to a canonical registry key (or unchanged)."""
    return fc.resolve_operator_name(name)


# ── Field vocabulary ────────────────────────────────────────────────────

#: Fields the export contract supplies, plus what the compiler computes for
#: itself. Anything outside this set is a genuine gap, not a spelling variant.
#:
#: The OHLC/VWAP/pre-close group moved here once `scripts/export_rqsdk_panel.py`
#: began exporting them: they used to be aspirational, now they are real.
PANEL_FIELDS: frozenset[str] = frozenset(
    {
        "CLOSE",
        "VOLUME",
        "AMOUNT",          # total_turnover
        "SHARES",          # circulation_a
        "LIMIT_UP",
        "LIMIT_DOWN",
        "LISTED_DATE",
        "DE_LISTED_DATE",
        "IS_ST",
        "IS_SUSPENDED",
        "OPEN",
        "HIGH",
        "LOW",
        "VWAP",
        "PRE_CLOSE",
        "INDUSTRY",
    }
)

#: Fields the catalog references that nothing supplies yet. Deriving them is a
#: concrete, bounded engine task. Until it lands they are gaps, and counting them
#: as available would overstate the candidate pool.
DERIVED_FIELDS: frozenset[str] = frozenset(
    {
        # `advN` is synthesised by the compiler from total_turnover; listed here
        # as available only for the N the compiler can build, which is any.
        *(f"ADV{n}" for n in range(1, 501)),
    }
)

#: Fields needing a separate RQData reference-data or financials feed.
RQDATA_ONLY_FIELDS: frozenset[str] = frozenset(
    {
        "CAP",
        "MARKET_CAP",
        "TOTAL_SHARES",
        "FREE_FLOAT",
        "SECTOR",
        "SUBINDUSTRY",
        "RETURNS",
        "DAILY_RETURN",
        "STOCK_RETURN",
        "MARKET_RETURN",
        "ASSETS",
        "EQUITY",
        "LIABILITIES",
        "NET_PROFIT_TTM",
        "REVENUE_TTM",
        "EPS_YOY",
        "PROFIT_YOY",
        "REVENUE_YOY",
    }
)


# ── Result types ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class FactorReadiness:
    """Readiness verdict for a single catalogued factor."""

    verdict: str
    operators_used: tuple[str, ...] = ()
    unresolved_operators: tuple[str, ...] = ()
    aliased_operators: tuple[str, ...] = ()
    fields_used: tuple[str, ...] = ()
    missing_fields: tuple[str, ...] = ()
    parse_error: str | None = None

    @property
    def runnable(self) -> bool:
        """True when the engine can evaluate this expression as it stands."""
        return self.verdict in ("runnable_now", "alias_only")

    def as_dict(self) -> dict[str, object]:
        return {
            "verdict": self.verdict,
            "operators_used": list(self.operators_used),
            "unresolved_operators": list(self.unresolved_operators),
            "aliased_operators": list(self.aliased_operators),
            "fields_used": list(self.fields_used),
            "missing_fields": list(self.missing_fields),
            "parse_error": self.parse_error,
        }


# ── AST walking ─────────────────────────────────────────────────────────

def _walk_calls(node: object, out: list[str]) -> None:
    if isinstance(node, fc.FuncCall):
        out.append(node.func.upper())
        for arg in node.args:
            _walk_calls(arg, out)
    elif isinstance(node, fc.BinOp):
        _walk_calls(node.left, out)
        _walk_calls(node.right, out)
    elif isinstance(node, fc.UnaryOp):
        _walk_calls(node.operand, out)
    elif isinstance(node, fc.IfExpr):
        _walk_calls(node.cond, out)
        _walk_calls(node.true_val, out)
        _walk_calls(node.false_val, out)


def _walk_fields(node: object, out: set[str]) -> None:
    if isinstance(node, fc.Field):
        out.add(node.name.upper())
    elif isinstance(node, fc.FuncCall):
        for arg in node.args:
            _walk_fields(arg, out)
    elif isinstance(node, fc.BinOp):
        _walk_fields(node.left, out)
        _walk_fields(node.right, out)
    elif isinstance(node, fc.UnaryOp):
        _walk_fields(node.operand, out)
    elif isinstance(node, fc.IfExpr):
        _walk_fields(node.cond, out)
        _walk_fields(node.true_val, out)
        _walk_fields(node.false_val, out)


def classify_expression(expression: str) -> FactorReadiness:
    """Classify one catalog expression into a readiness verdict."""
    try:
        ast = fc.Parser(fc.tokenize(expression)).parse()
    except Exception as exc:  # noqa: BLE001 - any parse failure is a verdict
        return FactorReadiness(
            verdict="unparsable",
            parse_error=f"{type(exc).__name__}: {exc}",
        )

    calls: list[str] = []
    _walk_calls(ast, calls)
    fields: set[str] = set()
    _walk_fields(ast, fields)

    unresolved: list[str] = []
    aliased: list[str] = []
    for raw in sorted(set(calls)):
        resolved = resolve_operator(raw)
        if resolved in SUPPORTED_OPERATORS:
            # A resolution that changes the spelling means a synonym was applied.
            if normalise_operator(resolved) != normalise_operator(raw):
                aliased.append(raw)
        else:
            unresolved.append(raw)

    known_universe = PANEL_FIELDS | DERIVED_FIELDS | RQDATA_ONLY_FIELDS
    missing = tuple(sorted(f for f in fields if f not in known_universe))

    # A field the panel cannot supply is as blocking as a missing operator: the
    # compiler would emit df["adv20"] and fail at call time. Folding it into the
    # verdict keeps "runnable" meaning "the engine can actually compute this".
    if unresolved:
        verdict = "needs_numerics"
    elif missing:
        verdict = "needs_fields"
    elif aliased:
        verdict = "alias_only"
    else:
        verdict = "runnable_now"

    return FactorReadiness(
        verdict=verdict,
        operators_used=tuple(sorted(set(calls))),
        unresolved_operators=tuple(unresolved),
        aliased_operators=tuple(aliased),
        fields_used=tuple(sorted(fields)),
        missing_fields=missing,
    )


def readiness_summary(verdicts) -> dict[str, object]:
    """Aggregate a stream of verdicts into counts plus operator blockers."""
    counts = {
        "runnable_now": 0,
        "alias_only": 0,
        "needs_numerics": 0,
        "needs_fields": 0,
        "unparsable": 0,
    }
    blockers: dict[str, int] = {}
    missing_fields: dict[str, int] = {}

    for v in verdicts:
        counts[v.verdict] = counts.get(v.verdict, 0) + 1
        for op in v.unresolved_operators:
            blockers[op] = blockers.get(op, 0) + 1
        for f in v.missing_fields:
            missing_fields[f] = missing_fields.get(f, 0) + 1

    total = sum(counts.values())
    runnable = counts["runnable_now"] + counts["alias_only"]
    return {
        "total": total,
        "counts": counts,
        "runnable": runnable,
        "runnable_ratio": (runnable / total) if total else 0.0,
        "operator_blockers": dict(
            sorted(blockers.items(), key=lambda kv: (-kv[1], kv[0]))
        ),
        "unknown_fields": dict(
            sorted(missing_fields.items(), key=lambda kv: (-kv[1], kv[0]))
        ),
    }
