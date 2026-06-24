"""AI-generated factor library — price/technical factors from OHLCV data.

Unlike jq_gm (which requires GM SDK for financial statement data),
ai_factors computes everything from OHLCV panel data using pandas.
No external API needed — works in CI and on Mac.

Factors are registered at runtime via expression_to_spec() from
mining_bridge.  The spec list grows as LLM-generated factors pass
structural check + IC evaluation.
"""

from __future__ import annotations

from contracts.factor_research import FactorResearchSpec

AI_FACTORS_LIBRARY = "ai_factors"
AI_FACTORS_VERSION = "v2026.06"

# ── Registered AI factor specs ──
# Populated at runtime as factors pass verification.
# Initially empty — factors are added by expression_to_spec().

_ai_specs: list[FactorResearchSpec] = []


def register_spec(spec: FactorResearchSpec) -> None:
    """Register a new AI-generated factor spec."""
    if spec.factor_name not in {s.factor_name for s in _ai_specs}:
        _ai_specs.append(spec)


def ai_factors_specs() -> list[FactorResearchSpec]:
    return list(_ai_specs)


AI_FACTORS_IMPLEMENTED = [
    s.factor_name for s in _ai_specs
]
