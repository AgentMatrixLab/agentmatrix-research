"""Catalog readiness: can we actually compute a catalogued factor, and with what?

The Factor DB catalog (`pages/factor-db-dashboard/data/factors.json`) ships 1058
factor definitions written in Qlib/WorldQuant expression syntax. Before any of
them can enter the validation pipeline we must know, per factor, whether the
repository's own expression engine can evaluate it.

This module answers that question mechanically and returns one of four
readiness verdicts. It exists because `formula_compiler.compile_formula` is not
a sufficient test: an unrecognised function name is emitted verbatim as Python
source (`CORRELATION(...)`), so the compile succeeds and the failure only
surfaces as a `NameError` at execution time.

Verdicts
--------
``runnable_now``
    Parses once the tokenizer accepts the ``$field`` sigil, and every function
    call resolves to an operator already registered in ``formula_compiler``.
``alias_only``
    Same, except some calls use a known synonym of a registered operator
    (``Ref`` for ``ts_delay``, ``Correlation`` for ``rolling_corr``, ...).
    Resolvable by an alias table alone; no new numerics required.
``needs_numerics``
    At least one call names an operator with no implementation and no synonym.
``unparsable``
    The expression does not parse even after the ``$`` sigil is removed.

Read-only: this module never writes to disk and never touches the network.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from . import formula_compiler as fc

__all__ = [
    "ALIAS_MAP",
    "PANEL_FIELDS",
    "DERIVED_FIELDS",
    "FactorReadiness",
    "classify_expression",
    "readiness_summary",
]

# ── Operator vocabulary ─────────────────────────────────────────────────

#: Operators the engine implements today.
SUPPORTED_OPERATORS: frozenset[str] = frozenset(
    set(fc._PANEL_OPERATORS)
    | set(fc._SERIES_OPERATORS)
    | set(fc._WIDE_OPERATORS)
    | {"IF", "SEQUENCE"}
)

#: Catalog spellings that map 1:1 onto an operator the engine already has.
#: Every entry must be numerically faithful; synonyms that would change the
#: result (e.g. ``Ref`` -> ``Delta``, which differences instead of shifting)
#: are deliberately routed through their correct primitive instead.
#:
#: Keys must be disjoint from :data:`SUPPORTED_OPERATORS` — a spelling the
#: registry already implements needs no alias, and listing it here would let a
#: later registry rename silently change what the factor computes.
ALIAS_MAP: dict[str, str] = {
    # level shifts / differences
    "REF": "ts_delay",
    "DELAY": "ts_delay",
    "TS_DELAY": "ts_delay",
    "TS_DELTA": "ts_delta",
    "DIFF": "ts_delta",
    # rolling statistics under their long-form catalog spellings
    "TS_SUM": "ts_sum",
    "TS_MEAN": "ts_mean",
    "TS_STD": "ts_std",
    "TS_MIN": "ts_min",
    "TS_MAX": "ts_max",
    "TS_PRODUCT": "ts_product",
    "STDDEV": "ts_std",
    "TS_ARGMAX": "ts_argmax",
    "TS_ARGMIN": "ts_argmin",
    "TS_DECAY_LINEAR": "ts_decay_linear",
    # correlation family
    "CORRELATION": "rolling_corr",
    "COVARIANCE": "rolling_cov",
    # cross-sectional
    "CS_RANK": "cross_sectional_rank",
    "CS_SCALE": "cross_sectional_scale",
    "INDNEUTRAL": "indneutralize",
    # conditional selection: Greater/Less are binary comparators, not window ops
    "GREATER": "np.where",
    "LESS": "np.where",
    "MAX2": "np.maximum",
    "MIN2": "np.minimum",
    "POWER": "signed_power",
    "SIGNEDPOWER": "signed_power",
    "SIGNED_POWER": "signed_power",
}


def normalise_operator(name: str) -> str:
    """Fold a catalog operator spelling to a comparison key.

    The catalog mixes conventions freely — ``Ts_DecayLinear``,
    ``TS_DECAY_LINEAR`` and ``DecayLinear`` all occur — so case and underscores
    are removed before lookup. Original spellings are always what gets reported
    back to the caller; this key is only used for resolution.
    """
    return name.upper().replace("_", "")


#: Registry keys and alias keys, both in normalised form.
_SUPPORTED_NORMALISED: frozenset[str] = frozenset(
    normalise_operator(name) for name in SUPPORTED_OPERATORS
)
_ALIAS_NORMALISED: dict[str, str] = {
    normalise_operator(k): v for k, v in ALIAS_MAP.items()
}

#: A normalised key may resolve as registered *or* as an alias, never both.
_AMBIGUOUS = sorted(set(_SUPPORTED_NORMALISED) & set(_ALIAS_NORMALISED))
if _AMBIGUOUS:  # pragma: no cover - import-time invariant
    raise RuntimeError(
        f"operator spellings resolve ambiguously: {_AMBIGUOUS}; "
        "an alias must not shadow a registered operator"
    )
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

#: Fields the catalog references that the panel must add before the factor is
#: computable. Split into "derive from the panel" vs "needs an RQData feed".
DERIVED_FIELDS: frozenset[str] = frozenset(
    {"OPEN", "HIGH", "LOW", "VWAP", "PRE_CLOSE", "RETURNS", "DAILY_RETURN"}
)
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


#: The sigil Qlib/WorldQuant expressions use for a raw data field.
FIELD_SIGIL = "$"


def classify_expression(expression: str) -> FactorReadiness:
    """Classify one catalog expression into a readiness verdict.

    The ``$`` sigil is stripped before parsing because the tokenizer does not
    accept it yet; teaching the tokenizer the sigil is a prerequisite the
    verdict implicitly assumes.
    """
    normalised = expression.replace(FIELD_SIGIL, "")
    try:
        ast = fc.Parser(fc.tokenize(normalised)).parse()
    except Exception as exc:  # noqa: BLE001 - any parse failure is a verdict
        return FactorReadiness(
            verdict="unparsable",
            parse_error=f"{type(exc).__name__}: {exc}",
        )

    calls: list[str] = []
    _walk_calls(ast, calls)
    fields: set[str] = set()
    _walk_fields(ast, fields)

    unknown = sorted({name for name in calls if normalise_operator(name) not in _SUPPORTED_NORMALISED})
    unresolved = tuple(n for n in unknown if normalise_operator(n) not in _ALIAS_NORMALISED)
    aliased = tuple(n for n in unknown if normalise_operator(n) in _ALIAS_NORMALISED)

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
        unresolved_operators=unresolved,
        aliased_operators=aliased,
        fields_used=tuple(sorted(fields)),
        missing_fields=missing,
    )


def readiness_summary(
    verdicts: Iterable[FactorReadiness],
) -> dict[str, object]:
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
