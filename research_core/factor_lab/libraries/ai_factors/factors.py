"""AI factor compute engine — OHLCV panel data, no external SDK needed.

Computes AI-generated price/technical factors directly from pandas.
Works anywhere without GM SDK.

Two modes:
  1. compute_ai_factors(panel, factor_names) — factor names → lookup specs → compute
  2. compute_expressions(panel, expressions) — expressions → parse → compute directly
"""

from __future__ import annotations

import pandas as pd

from research_core.factor_lab.mining_bridge import (
    parse_expression, _compute_directly,
)


def compute_expressions(
    panel: pd.DataFrame,
    expressions: list[str],
) -> pd.DataFrame:
    """Compute factor values directly from expressions (no spec registration needed).

    Args:
        panel: pd.DataFrame with [date, code, open, high, low, close, volume]
        expressions: list of Qlib expression strings

    Returns:
        pd.DataFrame with [date, code, *expressions_as_columns]
    """
    result = panel[["date", "code"]].copy()
    for expr in expressions:
        # Use expression as column name (safe version)
        col = expr.replace("$", "").replace(" ", "_").replace("(", "_").replace(")", "_").replace("/", "_").replace("-", "_")
        parsed = parse_expression(expr)
        if parsed is not None:
            values = _compute_directly(panel, parsed)
            if values is not None:
                result[col] = values.values
                continue
        result[col] = float("nan")
    return result


def compute_ai_factors(
    panel: pd.DataFrame,
    factor_names: list[str],
) -> pd.DataFrame:
    """Compute AI factor values from OHLCV panel (registered factors only).

    Args:
        panel: pd.DataFrame with [date, code, open, high, low, close, volume]
        factor_names: list of registered factor names

    Returns:
        pd.DataFrame with [date, code, *factor_names]
    """
    from research_core.factor_lab.libraries.ai_factors.specs import ai_factors_specs
    spec_map = {s.factor_name: s for s in ai_factors_specs()}

    result = panel[["date", "code"]].copy()
    for name in factor_names:
        spec = spec_map.get(name)
        if spec is None:
            result[name] = float("nan")
            continue
        expression = spec.metadata.get("source_expression", "")
        if not expression:
            result[name] = float("nan")
            continue
        parsed = parse_expression(expression)
        if parsed is not None:
            values = _compute_directly(panel, parsed)
            if values is not None:
                result[name] = values.values
                continue
        result[name] = float("nan")
    return result
