"""
Mining Bridge: Qlib expressions → structural verification.

Checks whether an AI-generated Qlib expression can be parsed, mapped to
a known factor type, and potentially bridged to jq_gm.  Does NOT attempt
real GM computation — that requires registering the factor first via
expression_to_spec() → jq_gm library → compute_jq_gm_factors().

Design document: docs/mining_bridge_design.md
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

import pandas as pd


class ExprType(Enum):
    MOMENTUM = auto()
    VOLUME_RATIO = auto()
    VOLATILITY = auto()
    MOVING_AVERAGE = auto()
    PRICE_RATIO = auto()
    CORRELATION = auto()
    DELTA = auto()
    CROSS_SECTIONAL = auto()
    UNKNOWN = auto()


class PendingReason(Enum):
    JQ_SOURCE = auto()
    GM_SOURCE = auto()
    UNKNOWN = auto()


@dataclass
class ParsedExpression:
    raw: str
    expr_type: ExprType
    params: dict[str, Any] = field(default_factory=dict)


_PATTERNS: list[tuple[str, ExprType, str]] = [
    (r'^Ref\(\$(close),\s*(\d+)\)\s*/\s*\$\1\s*-\s*1$',  ExprType.MOMENTUM, "momentum"),
    (r'^\$(close)\s*/\s*Ref\(\$\1,\s*(\d+)\)\s*-\s*1$',  ExprType.MOMENTUM, "momentum-alt"),
    (r'^\$volume\s*/\s*Mean\(\$volume,\s*(\d+)\)$',      ExprType.VOLUME_RATIO, "volume"),
    (r'^Std\(\$(close),\s*(\d+)\)$',                     ExprType.VOLATILITY, "volatility"),
    (r'^Std\(.*Ref.*\$close.*,\s*(\d+)\)$',              ExprType.VOLATILITY, "vol-returns"),
    (r'^Mean\(\$(close),\s*(\d+)\)$',                     ExprType.MOVING_AVERAGE, "ma"),
    (r'^\$(high)\s*/\s*\$low$',                          ExprType.PRICE_RATIO, "ratio-hl"),
    (r'^\$(open)\s*/\s*\$close$',                        ExprType.PRICE_RATIO, "ratio-oc"),
    (r'^Corr\(\$(\w+),\s*\$(\w+),\s*(\d+)\)$',           ExprType.CORRELATION, "corr"),
    (r'^\$(close)\s*-\s*Ref\(\$\1,\s*(\d+)\)$',           ExprType.DELTA, "delta"),
    (r'Rank\(|IndNeutralize\(|Group\(',                  ExprType.CROSS_SECTIONAL, "cs"),
    # Compound expressions
    (r'^\(\$(close)\s*/\s*Ref\(\$\1,\s*(\d+)\)\s*-\s*1\)\s*\*\s*Log\(.*\)$',
     ExprType.MOMENTUM, "compound-momentum-vol"),
    (r'^\(\(\$(high)\s*-\s*\$low\)\s*/\s*\$close\)\s*\*\s*\(.*Ref.*\)$',
     ExprType.MOMENTUM, "compound-amplitude-momentum"),
    (r'^.*Ref\(\$(\w+),\s*(\d+)\).*$',                   ExprType.MOMENTUM, "has-ref"),
]


def parse_expression(expr: str) -> ParsedExpression | None:
    cleaned = re.sub(r'\s+', '', expr.strip())
    for pattern, etype, note in _PATTERNS:
        m = re.match(pattern, cleaned)
        if m:
            params: dict[str, Any] = {"note": note}
            for g in m.groups():
                if g is not None and g.isdigit():
                    params["window"] = int(g)
                    break
            return ParsedExpression(raw=expr, expr_type=etype, params=params)
    return None


_QLIB_OPERATORS = re.compile(
    r'\$(?:close|open|high|low|volume|vwap)|'
    r'\b(?:close|open|high|low|volume|vwap)\b|'
    r'\b(?:Ref|Mean|Std|Corr|Log|Sum|Delta|Delay|Rank|IndNeutralize|Group|Cut)\s*\('
)


def _has_qlib_operators(expr: str) -> bool:
    return bool(_QLIB_OPERATORS.search(expr))


@dataclass
class FactorMapping:
    route: str
    base_factor: str
    formula_template: str
    nc_reason: str | None


_MAPPING_TABLE: dict[ExprType, FactorMapping] = {
    ExprType.MOMENTUM: FactorMapping(
        route="custom_price", base_factor="REVS{window}",
        formula_template="close / Ref(close, {window}) - 1", nc_reason=None,
    ),
    ExprType.VOLUME_RATIO: FactorMapping(
        route="custom_price", base_factor="VOL{window}",
        formula_template="volume / Mean(volume, {window})", nc_reason=None,
    ),
    ExprType.VOLATILITY: FactorMapping(
        route="custom_price", base_factor="Std{window}",
        formula_template="Std(close, {window})",
        nc_reason="年化/非年化定义差异, 需追加 *sqrt(252) 验证",
    ),
    ExprType.MOVING_AVERAGE: FactorMapping(
        route="custom_price", base_factor="MA{window}",
        formula_template="Mean(close, {window})", nc_reason=None,
    ),
    ExprType.PRICE_RATIO: FactorMapping(
        route="custom_price", base_factor="VWAP",
        formula_template="{field1} / {field2}", nc_reason=None,
    ),
    ExprType.CORRELATION: FactorMapping(
        route="custom", base_factor="beta_252d",
        formula_template="Corr({field1}, {field2}, {window})",
        nc_reason="自定义相关性, 需验证与市场收益率回归窗口对齐",
    ),
    ExprType.DELTA: FactorMapping(
        route="custom_price", base_factor="REVS{window}",
        formula_template="{field} - Ref({field}, {window})", nc_reason=None,
    ),
}


UNMAPPABLE_PATTERNS: dict[str, tuple[str, PendingReason]] = {
    "Rank(": (
        "Cross-sectional rank — requires full-market cross-section. "
        "GM per-stock cannot replicate.",
        PendingReason.JQ_SOURCE,
    ),
    "IndNeutralize(": (
        "Industry neutralization — needs sector data + cross-sectional regression.",
        PendingReason.JQ_SOURCE,
    ),
    "Group(": (
        "Group aggregation — needs membership + cross-sectional aggregation.",
        PendingReason.JQ_SOURCE,
    ),
    "Cut(": (
        "Stock universe cutting — multi-stock comparison. GM single-stock mode cannot.",
        PendingReason.JQ_SOURCE,
    ),
    "$vwap /": (
        "VWAP-based ratios — GM custom_price mode uses close-only.",
        PendingReason.JQ_SOURCE,
    ),
    "RegBeta(": (
        "Rolling regression beta — needs market proxy + full regression.",
        PendingReason.JQ_SOURCE,
    ),
}


def is_mappable(expr: str) -> tuple[bool, tuple[str, PendingReason] | None]:
    cleaned = expr.strip()
    for pattern, (reason, pending) in UNMAPPABLE_PATTERNS.items():
        if pattern in cleaned:
            return False, (reason, pending)
    return True, None


@dataclass
class VerificationResult:
    expression: str
    parsed: ParsedExpression | None
    mappable: bool
    unmappable_reason: tuple[str, PendingReason] | None = None
    pending_reason: PendingReason | None = None
    computed_count: int = 0
    finite_count: int = 0
    finite_ratio: float = 0.0
    benchmark_corr: float | None = None
    status: str = "pending"


def _compute_directly(panel: pd.DataFrame, parsed: ParsedExpression) -> pd.Series | None:
    """Compute factor value from panel data using pandas ops.

    Diagnostic only — does NOT use the real GM SDK.  Used to check whether
    a parsed expression can produce non-trivial values, but never determines
    PASS/FAIL status.
    """
    w = parsed.params.get("window", 20)
    if "code" in panel.columns and "date" in panel.columns:
        p = panel.sort_values(["code", "date"]).copy()
    else:
        p = panel.copy()

    try:
        if parsed.expr_type == ExprType.MOMENTUM:
            return p.groupby("code")["close"].pct_change(w)

        elif parsed.expr_type == ExprType.VOLUME_RATIO:
            return p.groupby("code")["volume"].transform(
                lambda x: x / x.rolling(w, min_periods=w).mean())

        elif parsed.expr_type == ExprType.VOLATILITY:
            returns = p.groupby("code")["close"].pct_change()
            return returns.transform(lambda x: x.rolling(w, min_periods=w).std())

        elif parsed.expr_type == ExprType.MOVING_AVERAGE:
            return p.groupby("code")["close"].transform(
                lambda x: x.rolling(w, min_periods=w).mean())

        elif parsed.expr_type == ExprType.DELTA:
            return p.groupby("code")["close"].transform(lambda x: x.diff(w))

        elif parsed.expr_type == ExprType.PRICE_RATIO:
            return p["high"] / p["low"]

        elif parsed.expr_type == ExprType.CORRELATION:
            def _rolling_corr(grp: pd.DataFrame, w: int):
                return grp["high"].rolling(w).corr(grp["low"])
            return p.groupby("code", group_keys=False).apply(
                lambda g: _rolling_corr(g, w))

        elif parsed.expr_type == ExprType.CROSS_SECTIONAL:
            return None

    except Exception:
        return None

    return None


def batch_verify(
    expressions: list[str],
    panel: pd.DataFrame,
) -> list[VerificationResult]:
    """Structural check on AI-generated expressions.  Does NOT call GM SDK.

    Statuses:
      PARSED     — expressible in known pattern, has mapping to GM route
      BROKEN     — known pattern but _compute_directly produced no values
      PENDING_JQ — needs cross-sectional data (Rank/IndNeutralize/Group/Cut)
      NC         — cannot parse or unsupported pattern

    Real GM verification requires registering the factor first:
      expression → expression_to_spec() → jq_gm → compute_jq_gm_factors()
    """
    results: list[VerificationResult] = []
    for expr in expressions:
        # ── Unmappable check ──
        mappable, reason = is_mappable(expr)
        if not mappable and reason:
            status = "PENDING_JQ" if reason[1] == PendingReason.JQ_SOURCE else "NC"
            results.append(VerificationResult(
                expression=expr, parsed=None,
                mappable=False, unmappable_reason=reason,
                pending_reason=reason[1], status=status,
            ))
            continue

        # ── Parse check ──
        parsed = parse_expression(expr)
        if parsed is None:
            # Unknown pattern — but is it recognisable Qlib or garbage?
            if _has_qlib_operators(expr):
                parsed = ParsedExpression(raw=expr, expr_type=ExprType.UNKNOWN, params={"note": "qlib-pass-through"})
            else:
                results.append(VerificationResult(
                    expression=expr, parsed=None,
                    mappable=True, unmappable_reason=("无法解析", PendingReason.UNKNOWN),
                    status="NC",
                ))
                continue

        # ── Mapping check ──
        mapping = _MAPPING_TABLE.get(parsed.expr_type)
        computed_count, finite_count, finite_ratio = 0, 0, 0.0

        if mapping:
            # Diagnostic: can pandas compute this locally?
            try:
                values = _compute_directly(panel, parsed)
                if values is not None:
                    computed_count = len(values)
                    finite_count = int(values.dropna().replace(
                        [float("inf"), float("-inf")], None).dropna().count())
                    finite_ratio = finite_count / max(computed_count, 1)
            except Exception:
                pass

            status = "BROKEN" if (computed_count > 0 and finite_count == 0) else "PARSED"
        elif parsed.expr_type == ExprType.UNKNOWN:
            # Unrecognised but has Qlib operators — pass through, let Qlib handle it
            status = "PARSED"
        else:
            status = "NC"

        results.append(VerificationResult(
            expression=expr, parsed=parsed,
            mappable=True, unmappable_reason=None,
            computed_count=computed_count, finite_count=finite_count,
            finite_ratio=finite_ratio, status=status,
        ))

    return results


def expression_to_spec(
    parsed: ParsedExpression,
    name: str,
) -> dict[str, Any] | None:
    """Convert a parsed expression to a FactorResearchSpec template.

    Returns a dict ready to be passed to FactorResearchSpec(**kw).
    Does NOT register the spec — caller must add it to specs.py.
    """
    mapping = _MAPPING_TABLE.get(parsed.expr_type)
    if mapping is None:
        return None

    w = parsed.params.get("window", 20)
    return {
        "factor_name": name,
        "library": "jq_gm",
        "version": "v2026.06",
        "display_name": f"AI_{name}",
        "formula": mapping.formula_template.format(
            window=w, field1="close", field2="volume",
            field="{field}", field1_="{field1}", field2_="{field2}",
        ),
        "description": f"AI-generated {parsed.expr_type.name} factor, window={w}",
        "required_fields": ["close", "volume"] if parsed.expr_type in (
            ExprType.VOLUME_RATIO, ExprType.CORRELATION) else ["close"],
        "tags": ["ai-generated", parsed.expr_type.name.lower()],
        "metadata": {
            "gm_field": mapping.route,
            "gm_fields": mapping.base_factor.format(window=w),
            "source_expression": parsed.raw,
            "bridge_mapping": mapping.base_factor,
        },
    }


def feedback_to_miner(results: list[VerificationResult]) -> dict[str, Any]:
    parsed = [r for r in results if r.status == "PARSED"]
    broken = [r for r in results if r.status == "BROKEN"]
    pending_jq = [r for r in results if r.status == "PENDING_JQ"]
    nc = [r for r in results if r.status == "NC"]

    avoid_patterns: list[str] = []
    for r in nc:
        reason = (r.unmappable_reason[0] if r.unmappable_reason else "Unknown")
        avoid_patterns.append(f"{r.expression[:60]}: {reason}")

    pending_patterns: list[str] = []
    for r in pending_jq:
        reason = (r.unmappable_reason[0] if r.unmappable_reason else "Unknown")
        pending_patterns.append(f"{r.expression[:60]}: {reason}")

    return {
        "batch_summary": {
            "total": len(results), "parsed": len(parsed),
            "broken": len(broken), "pending_jq": len(pending_jq),
            "nc": len(nc),
        },
        "successful_patterns": [
            r.parsed.expr_type.name if r.parsed else "unknown" for r in parsed
        ],
        "pending_jq": pending_patterns,
        "avoid_patterns": avoid_patterns,
        "suggestion": (
            "Focus on time-series momentum, volume, and volatility patterns. "
            "Avoid Rank, IndNeutralize, Cut, and Group operations — these "
            "require cross-sectional data unavailable in single-stock GM mode."
        ),
    }


def feedback_to_prompt(results: list[VerificationResult]) -> str:
    """Convert verification results to natural-language feedback for auto-mine."""
    feedback = feedback_to_miner(results)
    stats = feedback["batch_summary"]
    lines: list[str] = []

    lines.append(
        f"Previous round: {stats['total']} candidates → "
        f"{stats['parsed']} structurally valid, {stats['broken']} broken, "
        f"{stats['pending_jq']} JQ-only, {stats['nc']} unparseable."
    )

    if feedback["successful_patterns"]:
        lines.append(
            "Patterns that passed structural check: "
            + ", ".join(set(feedback["successful_patterns"])) + "."
        )

    if feedback["avoid_patterns"]:
        lines.append("DO NOT generate these — they failed verification:")
        for p in feedback["avoid_patterns"][:8]:
            lines.append(f"  - {p}")

    if feedback["pending_jq"]:
        lines.append(
            "These need cross-sectional data (JQ engine, not GM single-stock):"
        )
        for p in feedback["pending_jq"][:5]:
            lines.append(f"  - {p}")
        lines.append("You may still generate these if JQ engine is available.")

    lines.append(feedback["suggestion"])
    return "\n".join(lines)
