"""
jq_gm — JointQuant GM Factor Library for AgentMatrix Research.

Factors adapted from the JoinQuant factor board taxonomy, independently
implemented via the GM (掘金) SDK. 215 non-Alpha factors across 10
categories (basic, quality, momentum, growth, sentiment, per-share,
risk, technical indicators, and sub-categories).

=== Integration with factor_lab ===

This module follows the same pattern as libraries/alpha101 and
libraries/gtja191:

  specs.py    — FactorResearchSpec declarations (215 factors)
  factors.py  — compute engine wrapping gm_factor_lib.calc_factors()
  test_factors.py — unit tests for spec validity and compute routing

Every factor registered here passes through the standard factor_lab
pipeline: Spec → compute → proof-batch → validation report.

=== Note on GM SDK dependency ===

The compute engine requires the GM (掘金) SDK and a valid GM terminal
session.  In environments without GM SDK, the engine falls back to
stub mode (empty DataFrames) — sufficient for CI validation of the
pipeline, but not for numerical correctness checks.  See factors.py
for details.
"""

# Import specs and compute functions to expose at package level.
# Factors and specs modules import from external sources (gm_factor_lib)
# and are loaded lazily when first accessed.
from research_core.factor_lab.libraries.jq_gm.specs import (
    JQ_GM_IMPLEMENTED_FACTORS,
    JQ_GM_LIBRARY,
    JQ_GM_VERSION,
    jq_gm_specs,
    register_spec,
)

# compute_jq_gm_factors imported lazily — see factors.py for rationale.

__all__ = [
    "JQ_GM_IMPLEMENTED_FACTORS",
    "JQ_GM_LIBRARY",
    "JQ_GM_VERSION",
    "jq_gm_specs",
]
