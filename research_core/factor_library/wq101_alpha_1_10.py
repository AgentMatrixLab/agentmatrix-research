import pandas as pd
from research_core.factor_lab.libraries.factor_sets import compute_wq101_alphas


def compute_all_alphas(df: pd.DataFrame) -> pd.DataFrame:
    """Compatibility wrapper for the factor_lab Alpha101 1-10 implementation."""
    return compute_wq101_alphas(df)
