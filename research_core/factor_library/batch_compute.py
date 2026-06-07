# ============================================================
# Batch Factor Compute - 批量因子计算
# ============================================================

import pandas as pd
from .wq101_alpha_1_10 import compute_all_alphas as compute_wq101
from .gtja191_alpha_1_10 import compute_all_alphas as compute_gtja191


def compute_factor_set(df: pd.DataFrame, factor_set: str, factors: list[str] | None = None) -> pd.DataFrame:
    """Compute a named factor set and optionally select a subset of alpha columns.

    Parameters
    ----------
    df:
        OHLCV input with date, code, open, high, low, close, volume, amount.
    factor_set:
        Either ``"wq101"`` or ``"gtja191"``.
    factors:
        Optional list such as ``["alpha1", "alpha3"]``.
    """
    normalized = factor_set.lower()
    if normalized == 'wq101':
        result = compute_wq101(df.copy())
    elif normalized == 'gtja191':
        result = compute_gtja191(df.copy())
    else:
        raise ValueError(f"Unsupported factor_set: {factor_set}")

    if factors is None:
        return result

    missing = [factor for factor in factors if factor not in result.columns]
    if missing:
        raise ValueError(f"Unknown factors for {factor_set}: {missing}")
    return result[['date', 'code'] + factors].copy()


def batch_compute_factors(df, factor_sets=None):
    """
    批量计算多组因子

    参数:
        df: DataFrame, 输入数据
        factor_sets: list, 要计算的因子集合 ['wq101', 'gtja191']

    返回:
        DataFrame, 包含所有因子结果
    """
    if factor_sets is None:
        factor_sets = ['wq101', 'gtja191']

    results = []

    if 'wq101' in factor_sets:
        wq101_result = compute_factor_set(df, 'wq101')
        wq101_result.columns = ['date', 'code'] + [f'wq101_alpha{i}' for i in range(1, 11)]
        results.append(wq101_result)

    if 'gtja191' in factor_sets:
        gtja191_result = compute_factor_set(df, 'gtja191')
        gtja191_result.columns = ['date', 'code'] + [f'gtja191_alpha{i}' for i in range(1, 11)]
        results.append(gtja191_result)

    # 合并结果
    if len(results) == 1:
        return results[0]
    else:
        merged = results[0]
        for result in results[1:]:
            merged = pd.merge(merged, result, on=['date', 'code'], how='outer')
        return merged
