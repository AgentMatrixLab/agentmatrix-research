"""
jq_gm factor computation engine.

Wraps the GM (掘金) SDK calc_factors() from the external gm_factor_lib
module.  In environments where the GM SDK is not installed (CI, local
dev without a GM terminal), the module falls back to empty DataFrames
so the factor_lab pipeline can still validate Spec integrity.

=== Architecture ===

The compute function receives a demo data panel (date × code with OHLCV
columns) from the factor_lab service layer, but jq_gm factors do NOT
use this panel — they call the GM API directly with real securities
and date ranges.  The demo panel is only used for evaluation metrics
(IC, coverage ratio), not for factor computation itself.

In GM-stub mode (no SDK), we return a DataFrame with all factor columns
set to NaN, which is sufficient for:
  - Verifying that every Spec has a corresponding compute path
  - Testing the CLI / service plumbing
  - CI validation of the full pipeline

Real numerical verification (GM vs JQ truth comparison) must run
inside a GM terminal with valid credentials.

=== Usage ===

  from research_core.factor_lab.libraries.jq_gm.factors import (
      compute_jq_gm_factors,
  )

  # Panel: pd.DataFrame with columns [date, code, open, high, low, close, ...]
  factor_frame = compute_jq_gm_factors(panel, factor_names=["pe_ttm", "roe_ttm"])
  # Returns: pd.DataFrame with columns [date, code, pe_ttm, roe_ttm, ...]
"""

from __future__ import annotations

import pandas as pd

# ── Lazy import of gm_factor_lib ─────────────────────────────────
#
# gm_factor_lib lives outside this repo (in the CrossvalidationTYD
# project directory).  We attempt to import it; if unavailable, we
# operate in stub mode.

_GM_AVAILABLE = False
_calc_factors = None

try:
    # Path to gm_factor_lib in the CrossvalidationTYD project.
    # In production, users should symlink or pip-install gm_factor_lib.
    import sys
    from pathlib import Path

    _gm_lib_path = Path.home() / "Desktop" / "TYDQUANT" / "JQ2GM"
    if str(_gm_lib_path) not in sys.path:
        sys.path.insert(0, str(_gm_lib_path))

    from gm_factor_lib import calc_factors as _gm_calc_factors, GM_AVAILABLE as _GM_SDK_AVAILABLE  # type: ignore[import]

    _calc_factors = _gm_calc_factors
    _GM_AVAILABLE = bool(_GM_SDK_AVAILABLE)
except (ImportError, RuntimeError):
    _GM_AVAILABLE = False


def compute_jq_gm_factors(
    panel: pd.DataFrame,
    factor_names: list[str],
    *,
    securities: list[str] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    **kwargs,
) -> pd.DataFrame:
    """Compute factor values for the requested jq_gm factors.

    In GM-available mode: calls gm_factor_lib.calc_factors() with the
    given securities and date range, then pivots the result into the
    factor_lab expected wide format (date × code, one column per factor).

    In GM-stub mode: returns a DataFrame with all factor columns NaN.

    Args:
        panel:        Demo data panel (date, code, OHLCV columns).
        factor_names: List of factor names from JQ_GM_IMPLEMENTED_FACTORS.
        securities:   GM security codes (e.g. ['SHSE.600519']).
                      Required in GM-available mode.
        start_date:   Start date in YYYY-MM-DD format.
        end_date:     End date in YYYY-MM-DD format.

    Returns:
        pd.DataFrame with columns [date, code, *factor_names].
    """
    if not _GM_AVAILABLE:
        # Stub mode: return NaN-filled frame with correct columns.
        result = panel[["date", "code"]].copy()
        for name in factor_names:
            result[name] = float("nan")
        return result

    # GM-available mode: call the real engine.
    if securities is None:
        # Fallback: extract unique codes from the demo panel.
        # Panel codes are synthetic (e.g. 'stock_001'), so this only
        # works with real securities passed explicitly.
        securities = sorted(panel["code"].unique().tolist())

    if start_date is None:
        start_date = str(panel["date"].min())
    if end_date is None:
        end_date = str(panel["date"].max())

    raw = _calc_factors(
        securities=securities,
        factors=factor_names,
        start_date=start_date,
        end_date=end_date,
        use_real_price=kwargs.get("use_real_price", True),
        skip_paused=kwargs.get("skip_paused", True),
    )

    # raw: dict[str, pd.DataFrame]
    # Each DataFrame: index=trade_date, columns=symbols, values=factor_value
    # Transform to factor_lab wide format: date, code, factor_1, factor_2, ...

    frames = []
    for factor_name, df in raw.items():
        if df.empty:
            continue
        stacked = df.stack(future_stack=True).reset_index()
        stacked.columns = ["date", "code", factor_name]
        frames.append(stacked)

    if not frames:
        # All empty — return NaN frame.
        result = panel[["date", "code"]].copy()
        for name in factor_names:
            result[name] = float("nan")
        return result

    # Merge all factor DataFrames on (date, code)
    result = frames[0]
    for frame in frames[1:]:
        result = result.merge(frame, on=["date", "code"], how="outer")

    # Align with the demo panel's date/code grid.
    result = panel[["date", "code"]].merge(result, on=["date", "code"], how="left")

    # Ensure all requested factor columns exist.
    for name in factor_names:
        if name not in result.columns:
            result[name] = float("nan")

    return result[["date", "code", *factor_names]]
