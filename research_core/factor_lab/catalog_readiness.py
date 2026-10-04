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
    Parses and every function call resolves to an operator already registered.
``alias_only``
    Same, except some calls use a verified synonym of a registered operator
    (``Ref`` for ``ts_delay``, ``Correlation`` for ``rolling_corr``, ...).
    Resolvable by the spelling table alone; no new numerics required.
``needs_numerics``
    At least one call names an operator with no implementation and no verified
    synonym.
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

#: Fields the current offline panel contract (runbook_hermes.md §2) provides.
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
    }
)

#: Fields the catalog references that the panel export must add before the
#: factor is computable. These are derivable from RQData's daily quote feed.
DERIVED_FIELDS: frozenset[str] = frozenset(
    {"OPEN", "HIGH", "LOW", "VWAP", "PRE_CLOSE", "RETURNS", "DAILY_RETURN"}
)

#: Fields needing a separate RQData feed (reference data or financials).
RQDATA_ONLY_FIELDS: frozenset[str] = frozenset(
    {"CAP", "MARKET_CAP", "TOTAL_SHARES", "FREE_FLOAT", "INDUSTRY", "SECTOR"}
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

    if unresolved:
        verdict = "needs_numerics"
    elif aliased:
        verdict = "alias_only"
    else:
        verdict = "runnable_now"

    known_universe = PANEL_FIELDS | DERIVED_FIELDS | RQDATA_ONLY_FIELDS
    missing = tuple(sorted(f for f in fields if f not in known_universe))

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
