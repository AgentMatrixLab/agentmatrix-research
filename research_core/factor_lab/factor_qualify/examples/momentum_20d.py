"""
示例因子：20日动量（参考 AgentMatrix submissions/momentum_20d）

公式: (close_t - close_{t-20}) / close_{t-20}

这是量化里最经典的因子之一，用于演示和测试验证流水线。
"""

import pandas as pd


def compute(panel: pd.DataFrame) -> pd.Series:
    """计算20日收益率作为动量因子。

    Args:
        panel: DataFrame，必须包含 date, code, close 列

    Returns:
        pd.Series，因子值（20日涨跌幅），长度与 panel 一致
    """
    panel_sorted = panel.sort_values(["code", "date"]).reset_index(drop=True)
    result = panel_sorted.groupby("code")["close"].pct_change(20)
    result.index = panel_sorted.index
    return result.reindex(panel.index)
