"""
Mining Bridge: Qlib expressions → jq_gm factor Specs

Bridges the gap between AI-generated Qlib factor expressions and the
GM-based jq_gm factor validation pipeline.

Three core interfaces:
  1. parse_expression(expr) → ParsedExpression or None
  2. expression_to_spec(parsed, name) → FactorResearchSpec
  3. batch_verify(specs, panel) → dict[str, VerificationResult]

Design document: docs/mining_bridge_design.md
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Optional

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


@dataclass
class SubExpression:
    expr_type: ExprType
    params: dict[str, Any] = field(default_factory=dict)


_PATTERNS: list[tuple[str, ExprType, str]] = [
    # Momentum: Ref($close, N) / $close - 1
    (r'^Ref\(\$(close),\s*(\d+)\)\s*/\s*\$\1\s*-\s*1$',  ExprType.MOMENTUM, "momentum"),
    (r'^\$(close)\s*/\s*Ref\(\$\1,\s*(\d+)\)\s*-\s*1$',  ExprType.MOMENTUM, "momentum-alt"),
    # Volume ratio
    (r'^\$volume\s*/\s*Mean\(\$volume,\s*(\d+)\)$',      ExprType.VOLUME_RATIO, "volume"),
    # Volatility
    (r'^Std\(\$(close),\s*(\d+)\)$',                     ExprType.VOLATILITY, "volatility"),
    (r'^Std\(.*Ref.*\$close.*,\s*(\d+)\)$',              ExprType.VOLATILITY, "vol-returns"),
    # Moving average
    (r'^Mean\(\$(close),\s*(\d+)\)$',                     ExprType.MOVING_AVERAGE, "ma"),
    # Price ratio
    (r'^\$(high)\s*/\s*\$low$',                          ExprType.PRICE_RATIO, "ratio-hl"),
    (r'^\$(open)\s*/\s*\$close$',                        ExprType.PRICE_RATIO, "ratio-oc"),
    # Correlation
    (r'^Corr\(\$(\w+),\s*\$(\w+),\s*(\d+)\)$',           ExprType.CORRELATION, "corr"),
    # Delta
    (r'^\$(close)\s*-\s*Ref\(\$\1,\s*(\d+)\)$',           ExprType.DELTA, "delta"),
    # Cross-sectional ops — always unmappable
    (r'Rank\(|IndNeutralize\(|Group\(',                  ExprType.CROSS_SECTIONAL, "cs"),
    # ── Compound expressions ──
    # Momentum * log(volume_ratio): ($close / Ref($close, N) - 1) * Log(...)
    (r'^\(\$(close)\s*/\s*Ref\(\$\1,\s*(\d+)\)\s*-\s*1\)\s*\*\s*Log\(.*\)$',
     ExprType.MOMENTUM, "compound-momentum-vol"),
    # Amplitude * momentum: (($high-$low)/$close) * ($close/Ref($close,N)-1)
    (r'^\(\(\$(high)\s*-\s*\$(low)\)\s*/\s*\$(close)\)\s*\*\s*\(.*Ref.*\)$',
     ExprType.MOMENTUM, "compound-amplitude-momentum"),
    # Simple arithmetic with Ref: $(X) * Ref($(Y), N) etc
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
    """Compute factor value directly from panel data, bypassing FACTOR_REGISTRY.

    Handles time-series types (MOMENTUM, VOLATILITY, etc.) using pandas ops.
    Cross-sectional types (Rank, IndNeutralize) → returns None.
    """
    w = parsed.params.get("window", 20)
    # Ensure panel is sorted by code and date for shift operations
    if "code" in panel.columns and "date" in panel.columns:
        p = panel.sort_values(["code", "date"]).copy()
    else:
        p = panel.copy()

    field_map = {
        "open": "open", "high": "high", "low": "low",
        "close": "close", "volume": "volume", "vwap": "vwap",
    }

    try:
        if parsed.expr_type == ExprType.MOMENTUM:
            close = p.groupby("code")["close"]
            return close.pct_change(w)

        elif parsed.expr_type in (ExprType.VOLUME_RATIO,):
            vol = p.groupby("code")["volume"]
            return vol.transform(lambda x: x / x.rolling(w, min_periods=w).mean())

        elif parsed.expr_type == ExprType.VOLATILITY:
            close = p.groupby("code")["close"]
            returns = close.pct_change()
            return returns.transform(lambda x: x.rolling(w, min_periods=w).std())

        elif parsed.expr_type == ExprType.MOVING_AVERAGE:
            close = p.groupby("code")["close"]
            return close.transform(lambda x: x.rolling(w, min_periods=w).mean())

        elif parsed.expr_type == ExprType.DELTA:
            close = p.groupby("code")["close"]
            return close.transform(lambda x: x.diff(w))

        elif parsed.expr_type == ExprType.PRICE_RATIO:
            f1, f2 = "high", "low"
            for g in parsed.params.get("note", "").split():
                pass  # Could extract from expression
            return p["high"] / p["low"]

        elif parsed.expr_type == ExprType.CORRELATION:
            # rolling.corr(other) returns a Series per group
            def _rolling_corr(grp: pd.DataFrame, w: int):
                return grp["high"].rolling(w).corr(grp["low"])
            return p.groupby("code", group_keys=False).apply(
                lambda g: _rolling_corr(g, w)
            )

        elif parsed.expr_type == ExprType.CROSS_SECTIONAL:
            return None  # Needs full market cross-section

    except Exception:
        return None

    return None


def batch_verify(
    expressions: list[str],
    panel: pd.DataFrame,
    *,
    compute_fn=None,
    benchmark_factors: dict[str, pd.Series] | None = None,
) -> list[VerificationResult]:
    if compute_fn is None:
        try:
            from research_core.factor_lab.libraries.jq_gm.factors import \
                compute_jq_gm_factors
            compute_fn = compute_jq_gm_factors
        except ImportError:
            pass

    results: list[VerificationResult] = []
    for expr in expressions:
        mappable, result = is_mappable(expr)
        if not mappable and result:
            reason, pending = result
            status = "PENDING_JQ" if pending == PendingReason.JQ_SOURCE else "NC"
            results.append(VerificationResult(
                expression=expr, parsed=None,
                mappable=False, unmappable_reason=result, pending_reason=pending,
                status=status,
            ))
            continue

        parsed = parse_expression(expr)
        if parsed is None:
            results.append(VerificationResult(
                expression=expr, parsed=None,
                mappable=True, unmappable_reason=("无法解析", PendingReason.UNKNOWN),
                status="NC",
            ))
            continue

        mapping = _MAPPING_TABLE.get(parsed.expr_type)
        name = f"ai_{parsed.expr_type.name.lower()}_{parsed.params.get('window', 0)}"
        computed_count, finite_count, finite_ratio = 0, 0, 0.0
        status = "PENDING_GM"

        if mapping:
            # ── Try real jq_gm compute first ──
            if compute_fn is not None:
                try:
                    real_values = compute_fn(panel, [name])
                    if real_values is not None and name in real_values.columns:
                        vals = real_values[name]
                        computed_count = len(vals)
                        finite_count = int(vals.dropna().replace(
                            [float("inf"), float("-inf")], None).dropna().count())
                        finite_ratio = finite_count / max(computed_count, 1)
                        if finite_count > 0 and finite_ratio >= 0.3:
                            status = "PASS"
                        else:
                            status = "FAIL"
                except Exception:
                    pass

            # ── Fallback: _compute_directly for diagnostics only ──
            if status == "PENDING_GM":
                try:
                    values = _compute_directly(panel, parsed)
                    if values is not None:
                        computed_count = len(values)
                        finite_count = int(values.dropna().replace(
                            [float("inf"), float("-inf")], None).dropna().count())
                        finite_ratio = finite_count / max(computed_count, 1)
                except Exception:
                    pass
        else:
            # No mapping → unsupported expression type
            status = "NC"

        results.append(VerificationResult(
            expression=expr, parsed=parsed,
            mappable=True, unmappable_reason=None,
            computed_count=computed_count, finite_count=finite_count,
            finite_ratio=finite_ratio, status=status,
        ))

    return results


def feedback_to_miner(results: list[VerificationResult]) -> dict[str, Any]:
    passed = [r for r in results if r.status == "PASS"]
    failed = [r for r in results if r.status == "FAIL"]
    pending_jq = [r for r in results if r.status == "PENDING_JQ"]
    pending_gm = [r for r in results if r.status == "PENDING_GM"]
    nc = [r for r in results if r.status == "NC"]
    unknown = [r for r in results if r.status == "UNKNOWN"]

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
            "total": len(results), "passed": len(passed),
            "failed": len(failed), "pending_jq": len(pending_jq),
            "pending_gm": len(pending_gm), "nc": len(nc), "unknown": len(unknown),
        },
        "successful_patterns": [
            r.parsed.expr_type.name if r.parsed else "unknown" for r in passed
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
    """Convert verification results to natural-language feedback for auto-mine.

    Returns a compact prompt fragment that can be injected into the LLM's
    system prompt for the next iteration.  Only includes actionable
    information — patterns to avoid and patterns that work.
    """
    feedback = feedback_to_miner(results)
    stats = feedback["batch_summary"]
    lines: list[str] = []

    # Round summary
    lines.append(
        f"Previous round: {stats['total']} candidates → "
        + f"{stats['passed']} PASS, {stats['failed']} FAIL, "
        + f"{stats['pending_jq']} JQ-only, {stats['nc']} unparseable."
    )

    # Successful patterns to encourage
    if feedback["successful_patterns"]:
        lines.append(
            "Patterns that passed verification: "
            + ", ".join(set(feedback["successful_patterns"])) + "."
        )

    # Patterns to avoid
    if feedback["avoid_patterns"]:
        lines.append("DO NOT generate these — they failed verification:")
        for p in feedback["avoid_patterns"][:8]:
            lines.append(f"  - {p}")

    # Cross-sectional — label as JQ-required, not useless
    if feedback["pending_jq"]:
        lines.append(
            "These need cross-sectional data (JQ engine, not GM single-stock):"
        )
        for p in feedback["pending_jq"][:5]:
            lines.append(f"  - {p}")
        lines.append("You may still generate these if JQ engine is available.")

    # Core guidance
    lines.append(feedback["suggestion"])

    return "\n".join(lines)
