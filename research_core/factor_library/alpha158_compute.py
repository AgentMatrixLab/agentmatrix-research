# ============================================================
# Alpha158 Factor Compute Bridge
# ============================================================

import pandas as pd

from research_core.factor_lab.libraries.factor_sets import compute_alpha158_alphas


def compute_all_alphas(df: pd.DataFrame) -> pd.DataFrame:
    """Compute all Alpha158 (158) factors from a panel DataFrame.

    Parameters
    ----------
    df:
        OHLCV input with date, code, open, high, low, close, volume,
        and either vwap or amount columns.

    Returns
    -------
        DataFrame with date, code and 158 factor columns.
    """
    return compute_alpha158_alphas(df)
