"""
research_core — AgentMatrix AI-friendly research framework.

Usage:
    from research_core import discover, validate_factor, list_factors
    caps = discover()
    v = validate_factor("alpha101_001", ic_mean=0.045, ic_ir=0.65)
"""

from research_core.agent_api import (
    # meta
    discover,
    overview,
    # data & exploration
    check_data_source,
    explore_factors,
    # factor management
    validate_factor,
    evaluate_factor_csv,
    list_factors,
    # strategy & backtest
    build_strategy,
    package_backtest,
    parse_backtest_result,
    # Qlib
    mine_factor,
    auto_mine,
    qlib_backtest,
)

from research_core.agent_manifest import (
    get_manifest,
    get_capability,
    get_capabilities_by_category,
    manifest_to_markdown,
)

__all__ = [
    "discover",
    "overview",
    "check_data_source",
    "explore_factors",
    "validate_factor",
    "evaluate_factor_csv",
    "list_factors",
    "build_strategy",
    "package_backtest",
    "parse_backtest_result",
    "mine_factor",
    "auto_mine",
    "qlib_backtest",
    "get_manifest",
    "get_capability",
    "get_capabilities_by_category",
    "manifest_to_markdown",
]
