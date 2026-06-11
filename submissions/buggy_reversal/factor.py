"""
一个有bug的因子: 反转因子（公式方向写反了）
"""
import pandas as pd

def compute(panel: pd.DataFrame) -> pd.Series:
    """BUG: 应该是 -(P_t/P_{t-5} - 1)，但这里漏了负号"""
    # 错误: 应该加负号，短端反转应为 -reversal
    panel_sorted = panel.sort_values(["code", "date"]).reset_index(drop=True)
    result = panel_sorted.groupby("code")["close"].pct_change(5)
    result.index = panel_sorted.index
    return result.reindex(panel.index)
