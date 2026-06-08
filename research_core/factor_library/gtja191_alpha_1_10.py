from __future__ import annotations

import pandas as pd

from research_core.factor_lab.libraries.gtja191 import compute_gtja191_alphas


def compute_all_alphas(df: pd.DataFrame) -> pd.DataFrame:
    """Compatibility wrapper for the factor_lab GTJA191 Alpha1-10 implementation."""
    return compute_gtja191_alphas(df)
