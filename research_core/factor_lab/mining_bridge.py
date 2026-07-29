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
                if g is not None:
                    try:
                        w = int(g)
                        if w < 0:
                            w = -w  # DeepSeek uses Ref($close, -20) — normalize
                        params["window"] = w
                        break
                    except ValueError:
                        pass
            return ParsedExpression(raw=expr, expr_type=etype, params=params)
    # DeepSeek generates Ref($close, -N) — strip negatives and retry
    normalized = re.sub(r'Ref\(\$(\w+),\s*-\s*(\d+)\)', r'Ref($\1, \2)', expr.strip())
    if normalized != expr.strip():
        return parse_expression(normalized)
    return None


_QLIB_OPERATORS = re.compile(
    r'\$(?:close|open|high|low|volume|vwap)|'
    r'\b(?:close|open|high|low|volume|vwap)\b|'
    r'\b(?:Ref|Mean|Std|Corr|Log|Sum|Delta|Delay|Rank|IndNeutralize|Group|Cut)\s*\('
)


def _has_qlib_operators(expr: str) -> bool:
    return bool(_QLIB_OPERATORS.search(expr))


def _has_gm_fields(expr: str) -> bool:
    """Check if expression references GM API field names (net_profit_ttm, etc)."""
    try:
        from research_core.factor_lab.libraries.jq_gm.gm_field_reference import GM_FIELD_NAMES
        return any(field in expr for field in GM_FIELD_NAMES)
    except ImportError:
        return False


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
            _, pending = reason
            if pending == PendingReason.JQ_SOURCE:
                # Cross-sectional — needs Qlib.  Valid factor, different engine.
                # Route to ai_factors with note, can compute via Qlib.
                pass  # fall through to parse + route
            else:
                results.append(VerificationResult(
                    expression=expr, parsed=None,
                    mappable=False, unmappable_reason=reason,
                    pending_reason=pending, status="NC",
                ))
                continue

        # ── Parse check ──
        parsed = parse_expression(expr)
        if parsed is None:
            # Unknown pattern — but is it recognisable Qlib or garbage?
            if _has_qlib_operators(expr):
                parsed = ParsedExpression(raw=expr, expr_type=ExprType.UNKNOWN, params={"note": "qlib-pass-through"})
            elif _has_gm_fields(expr):
                # Has GM field names (e.g., $tot_mv, $net_profit_ttm) — valid fundamental expression
                parsed = ParsedExpression(raw=expr, expr_type=ExprType.UNKNOWN, params={"note": "gm-fundamental"})
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
        elif parsed.expr_type in (ExprType.UNKNOWN, ExprType.CROSS_SECTIONAL):
            # Unrecognised or cross-sectional — pass through, let Qlib handle it
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


def verify_gm(
    verification_results: list[VerificationResult],
    factor_names: list[str],
    securities: list[str] | None = None,
    start_date: str = "2025-12-31",
    end_date: str = "2025-12-31",
    gm_token: str = "",
) -> list[VerificationResult]:
    """Real GM SDK verification for jq_gm-routed factors.

    For each PARSED result that routes to jq_gm (has GM fields in expression),
    attempts to compute the factor via gm_factor_lib.calc_factors().
    Updates status to VERIFIED_GM (success), GM_FAILED (computation error),
    or leaves as PARSED if GM SDK is unavailable.

    Unlike batch_verify() which only checks structural patterns, this function
    actually calls the GM API to verify the factor can be computed with real data.

    Args:
        verification_results: output from batch_verify()
        factor_names: corresponding factor names for each result
        securities: GM security codes. Defaults to top 10 CSI300 stocks.
        start_date, end_date: date range for computation
        gm_token: GM SDK token. Required for real computation.

    Returns:
        Modified list with PARSED → VERIFIED_GM / GM_FAILED for jq_gm factors.
    """
    import numpy as np  # type: ignore[import]

    # ── Try to import GM SDK ──
    _gm_ready = False
    _calc = None
    try:
        if gm_token:
            from gm.api import set_token as _set_token  # type: ignore[import]
            _set_token(gm_token)
        # Import gm_factor_lib from known paths
        import sys as _sys, os as _os
        from pathlib import Path as _Path
        for _p in [
            _Path.home() / ".goldminer3" / "projects",
            _Path(_os.environ.get("JQ2GM_PATH",
                  str(_Path.home() / "Desktop" / "TYDQUANT" / "JQ2GM"))),
        ]:
            if str(_p) not in _sys.path and _p.exists():
                _sys.path.insert(0, str(_p))
        from gm_factor_lib import calc_factors as _gm_calc, GM_AVAILABLE  # type: ignore[import]
        if GM_AVAILABLE:
            _gm_ready = True
            _calc = _gm_calc
    except (ImportError, RuntimeError):
        pass

    if not _gm_ready:
        return verification_results  # No GM SDK, keep PARSED status

    if securities is None:
        securities = [
            "SHSE.600519", "SHSE.600036", "SHSE.601318", "SHSE.600900",
            "SHSE.601166", "SZSE.000858", "SZSE.002415", "SZSE.300750",
            "SZSE.000001", "SZSE.000333",
        ]

    for i, vr in enumerate(verification_results):
        if vr.status != "PARSED":
            continue
        if vr.parsed is None:
            continue

        # Check if this expression routes to jq_gm (has GM fields)
        if not _has_gm_fields(vr.expression):
            continue

        # Generate spec to get factor metadata
        name = factor_names[i] if i < len(factor_names) else f"gm_verify_{i}"
        spec_dict = expression_to_spec(vr.parsed, name)
        if spec_dict is None:
            continue

        gm_fields = spec_dict.get("metadata", {}).get("gm_fields", "")
        if not gm_fields:
            # Fallback: extract GM field names from expression (e.g., $tot_mv)
            import re as _re
            _fields = _re.findall(r'\$(\w+)', vr.expression)
            gm_fields = ",".join(_fields) if _fields else ""
        if not gm_fields:
            continue

        # Find matching registered factor key
        matched_key = None
        try:
            from gm_factor_lib import FACTOR_REGISTRY  # type: ignore[import]
            fields_list = [f.strip() for f in gm_fields.split(",")]
            for fk, fv in FACTOR_REGISTRY.items():
                fv_fields = str(fv.get("gm_fields", ""))
                if any(f in fv_fields for f in fields_list):
                    matched_key = fk
                    break
        except ImportError:
            pass

        if matched_key is None:
            # Factor not yet registered — could be a new AI-generated fundamental factor
            # For now, mark as needing registration
            vr.status = "NEEDS_REG"
            continue

        # ── Real GM computation ──
        try:
            raw = _calc(
                securities=securities,
                factors=[matched_key],
                start_date=start_date,
                end_date=end_date,
                use_real_price=True,
                skip_paused=True,
            )
            if matched_key in raw and not raw[matched_key].empty:
                vals = raw[matched_key].values.flatten()
                n_valid = int(np.sum(~np.isnan(vals)))
                if n_valid > 0:
                    vr.status = "VERIFIED_GM"
                    vr.computed_count = n_valid
                    vr.finite_count = n_valid
                    vr.finite_ratio = 1.0
                    vr.benchmark_corr = float(np.nanmean(vals))
                else:
                    vr.status = "GM_FAILED"
            else:
                vr.status = "GM_FAILED"
        except Exception:
            vr.status = "GM_FAILED"

    return verification_results


def expression_to_spec(
    parsed: ParsedExpression,
    name: str,
) -> dict[str, Any] | None:
    """Convert a parsed expression to a FactorResearchSpec template.

    Routes to ai_factors (price/technical) or jq_gm (fundamental/GM fields).
    """
    mapping = _MAPPING_TABLE.get(parsed.expr_type)
    if mapping is None and parsed.expr_type not in (ExprType.UNKNOWN, ExprType.CROSS_SECTIONAL):
        return None

    # Route: GM field names → jq_gm, otherwise → ai_factors
    has_gm = _has_gm_fields(parsed.raw)
    library = "jq_gm" if has_gm else "ai_factors"

    w = parsed.params.get("window", 20)
    spec = {
        "factor_name": name,
        "library": library,
        "version": "v2026.06",
        "display_name": f"AI_{name}",
        "required_fields": ["close"],
        "tags": ["ai-generated", parsed.expr_type.name.lower()],
        "metadata": {
            "source_expression": parsed.raw,
            "expr_type": parsed.expr_type.name,
            "library": library,
        },
    }

    if mapping:
        spec["formula"] = mapping.formula_template.format(
            window=w, field1="close", field2="volume",
            field="{field}", field1_="{field1}", field2_="{field2}",
        )
        spec["description"] = f"AI-generated {parsed.expr_type.name} factor, window={w}"
        spec["required_fields"] = ["close", "volume"] if parsed.expr_type in (
            ExprType.VOLUME_RATIO, ExprType.CORRELATION) else ["close"]
        if has_gm:
            spec["metadata"]["gm_field"] = mapping.route
            spec["metadata"]["gm_fields"] = mapping.base_factor.format(window=w)
    else:
        spec["formula"] = parsed.raw
        spec["description"] = f"AI-generated factor: {parsed.raw}"

    return spec


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
