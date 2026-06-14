"""
20日动量因子。

公式: (P_t - P_{t-20}) / P_{t-20}

这是最简单的动量因子之一，常用于演示因子提交流程。
"""
import pandas as pd


def compute(panel: pd.DataFrame) -> pd.Series:
    """计算 20 日收益率作为动量因子值。

    Args:
        panel: DataFrame，必须包含 date, code, close 列

    Returns:
        pd.Series，因子值（20日收益率），长度与 panel 一致
    """
    # 按股票分组，计算 20 日涨跌幅
    panel_sorted = panel.sort_values(["code", "date"]).reset_index(drop=True)
    result = panel_sorted.groupby("code")["close"].pct_change(20)

    # 对齐回原始 panel 索引
    result.index = panel_sorted.index
    # 重新按 panel 原始顺序排列
    return result.reindex(panel.index)
