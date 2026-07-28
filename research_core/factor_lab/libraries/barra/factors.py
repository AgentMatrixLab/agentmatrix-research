"""
Barra 风险因子计算 — 从回测引擎 barra_4factor.py 提取, 重构为独立的因子计算函数。

输入: pd.DataFrame, 需包含 financial 数据列:
  - symbol, trade_date
  - total_assets, total_liabilities, total_equity, net_profit

输出: 附加了 BP, EY, Lev, NLS 列的 DataFrame

与 barra_4factor.py 的 get_signals() 中间计算结果完全一致。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from research_core.factor_lab.libraries.barra.specs import IMPLEMENTED_BARRA_FACTORS


def compute_barra_factors(
    df: pd.DataFrame,
    factor_names: list[str] | None = None,
    *,
    finance_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    计算 Barra 风格因子值。

    参数:
        df: 包含 symbol 和金融字段的 DataFrame
        factor_names: 要计算的因子名列表, None = 全部
        finance_df: 外部传入的财务报表 DataFrame (可选)。
                   如果为 None, 则从 df 中读取 finance 列。
                   如果 df 已经包含 finance 列 (通过 merge 传入), 直接使用。

    返回:
        附加了因子列 (BP, EY, Lev, NLS) 的 DataFrame
    """
    requested = list(factor_names or IMPLEMENTED_BARRA_FACTORS)
    invalid = [n for n in requested if n not in IMPLEMENTED_BARRA_FACTORS]
    if invalid:
        raise ValueError(
            f"Unsupported Barra factors: {invalid}. "
            f"Available: {IMPLEMENTED_BARRA_FACTORS}"
        )

    result = df.copy()

    # 确定使用哪个数据源
    if finance_df is not None:
        result = result.merge(finance_df, on=["symbol"], how="left")
    elif "total_assets" not in result.columns:
        raise ValueError(
            "DataFrame 缺少金融字段 (total_assets, total_equity 等)。"
            "请 merge 财务报表数据后再调用, 或传入 finance_df 参数。"
        )

    total_assets = result["total_assets"].clip(lower=1)

    # ── BP: 账面市值比 ──
    if "BP" in requested and "total_equity" in result.columns:
        result["BP"] = result["total_equity"] / total_assets

    # ── EY: 盈利收益率 ──
    if "EY" in requested:
        net_profit = (
            result["net_profit"].fillna(0)
            if "net_profit" in result.columns
            else pd.Series(0.0, index=result.index)
        )
        result["EY"] = net_profit / total_assets

    # ── Lev: 杠杆 (取反) ──
    if "Lev" in requested and "total_liabilities" in result.columns:
        result["Lev"] = -result["total_liabilities"] / total_assets

    # ── NLS: 非线性市值 ──
    if "NLS" in requested:
        size = np.log(total_assets.clip(lower=1e6))
        size2 = size**2
        A = np.column_stack([np.ones(len(result)), size.values])
        coeff, _, _, _ = np.linalg.lstsq(A, size2.values, rcond=None)
        result["NLS"] = size2 - A @ coeff

    return result
