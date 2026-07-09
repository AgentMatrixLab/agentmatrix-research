# ============================================================
# Batch Factor Compute - 批量因子计算
# ============================================================

import pandas as pd

from research_core.factor_lab.libraries.factor_sets import compute_factor_set as compute_factor_lab_set


def compute_factor_set(df: pd.DataFrame, factor_set: str, factors: list[str] | None = None) -> pd.DataFrame:
    """Compute a named factor set and optionally select a subset of alpha columns.

    Parameters
    ----------
    df:
        OHLCV input with date, code, open, high, low, close, volume, amount.
    factor_set:
        One of ``"wq101"``, ``"gtja191"``, or ``"alpha158"``.
    factors:
        Optional list such as ``["alpha1", "alpha3"]`` or ``["KMID", "ROC5"]``.
    """
    result = compute_factor_lab_set(df.copy(), factor_set, factor_names=factors)

    return result


def batch_compute_factors(df, factor_sets=None):
    """
    批量计算多组因子

    参数:
        df: DataFrame, 输入数据
        factor_sets: list, 要计算的因子集合 ['wq101', 'gtja191', 'alpha158']

    返回:
        DataFrame, 包含所有因子结果
    """
    if factor_sets is None:
        factor_sets = ['wq101', 'gtja191']

    results = []

    for factor_set in factor_sets:
        result = compute_factor_set(df, factor_set)
        factor_columns = [column for column in result.columns if column not in {"date", "code"}]
        renamed = result.rename(columns={column: f"{factor_set}_{column}" for column in factor_columns})
        results.append(renamed)

    if not results:
        return df[["date", "code"]].copy()
    if len(results) == 1:
        return results[0]
    merged = results[0]
    for result in results[1:]:
        merged = pd.merge(merged, result, on=["date", "code"], how="outer")
    return merged
