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


_PATTERNS: list[tuple[str, ExprType, str]] = [
    (r'^Ref\(\$(\w+),\s*(\d+)\)\s*/\s*\$(\1)\s*-\s*1$',  ExprType.MOMENTUM, "momentum"),
    (r'^\$(\w+)\s*/\s*Ref\(\$(\1),\s*(\d+)\)\s*-\s*1$',  ExprType.MOMENTUM, "momentum-alt"),
    (r'^\$volume\s*/\s*Mean\(\$volume,\s*(\d+)\)$',      ExprType.VOLUME_RATIO, "volume"),
    (r'^Std\(\$(\w+),\s*(\d+)\)$',                       ExprType.VOLATILITY, "volatility"),
    (r'^Std\(.*Ref.*\$\w+.*,\s*(\d+)\)$',                ExprType.VOLATILITY, "vol-returns"),
    (r'^Mean\(\$(\w+),\s*(\d+)\)$',                       ExprType.MOVING_AVERAGE, "ma"),
    (r'^\$(\w+)\s*/\s*\$(\w+)$',                          ExprType.PRICE_RATIO, "ratio"),
    (r'^Corr\(\$(\w+),\s*\$(\w+),\s*(\d+)\)$',            ExprType.CORRELATION, "corr"),
    (r'^\$(\w+)\s*-\s*Ref\(\$(\1),\s*(\d+)\)$',           ExprType.DELTA, "delta"),
    (r'Rank\(|IndNeutralize\(|Group\(',                   ExprType.CROSS_SECTIONAL, "cs"),
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
        status = "PASS"

        if compute_fn and mapping:
            try:
                result_frame = compute_fn(panel, [name])
                factor_cols = [c for c in result_frame.columns if c not in ("date", "code")]
                if factor_cols:
                    values = result_frame[factor_cols[0]]
                    computed_count = len(values)
                    finite_vals = values.dropna().replace([float("inf"), float("-inf")], None)
                    finite_count = int(finite_vals.dropna().count())
                    finite_ratio = finite_count / max(computed_count, 1)
                    if finite_count == 0 and computed_count > 0:
                        status = "PENDING_GM"
                    elif finite_ratio < 0.8:
                        status = "FAIL"
            except Exception:
                status = "FAIL"

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
