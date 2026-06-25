"""AI-generated factor library.

Compute engine works from OHLCV panel — no external SDK needed.
Factors registered at runtime from LLM-generated expressions.
"""

from research_core.factor_lab.libraries.ai_factors.specs import (
    AI_FACTORS_IMPLEMENTED,
    AI_FACTORS_LIBRARY,
    AI_FACTORS_VERSION,
    ai_factors_specs,
    register_spec,
)

from research_core.factor_lab.libraries.ai_factors.factors import (
    compute_ai_factors,
)
