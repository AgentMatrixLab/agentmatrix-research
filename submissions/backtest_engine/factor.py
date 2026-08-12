"""
A股多因子复合信号 — 从回测引擎策略框架提取。

复合因子:
  1. 短期动量 (ret_5d):  5日收益, 追涨
  2. 中期反转 (-ret_20d): 负20日收益, 反转效应
  3. 低波动 (-vol_20d):  负20日波动率, 低波偏好
  4. 低换手 (-turnover): 负5日均换手率, 流动性过滤

等权 Z-score 标准化后复合。
"""
import pandas as pd
import numpy as np


def compute(panel: pd.DataFrame) -> pd.Series:
    """计算 A 股多因子复合得分。

    Args:
        panel: DataFrame，必须包含 date, code, close, volume, amount 列

    Returns:
        pd.Series，因子值（越高越好），长度与 panel 一致
    """
    panel = panel.sort_values(["code", "date"]).reset_index(drop=True)

    grouped = panel.groupby("code")

    # ── 因子1: 5日动量 (ret_5d) ──
    ret_5d = grouped["close"].pct_change(5)

    # ── 因子2: 20日反转 (-ret_20d) ──
    ret_20d = grouped["close"].pct_change(20)

    # ── 因子3: 20日波动率 (取负，偏好低波) ──
    ret_1d = grouped["close"].pct_change(1)
    vol_20d = ret_1d.transform(lambda x: x.rolling(20).std())

    # ── 因子4: 5日均换手率 (取负，偏好低换手) ──
    # 换手率 ≈ amount / (volume均价 * 流通股本), 这里用 amount/close 做代理
    proxy_turnover = panel["amount"] / panel["close"].clip(lower=0.01)
    turnover_5d = proxy_turnover.groupby(panel["code"]).transform(
        lambda x: x.rolling(5).mean()
    )

    # ── Z-score 截面标准化 ──
    def cross_sectional_zscore(series: pd.Series, date_col: pd.Series) -> pd.Series:
        """按日期做截面 Z-score 标准化"""
        df = pd.DataFrame({"date": date_col, "value": series})
        result = df.groupby("date")["value"].transform(
            lambda x: (x - x.mean()) / x.std() if x.std() > 1e-12 else 0.0
        )
        return result.fillna(0.0)

    f1 = cross_sectional_zscore(ret_5d, panel["date"])        # 动量
    f2 = cross_sectional_zscore(-ret_20d, panel["date"])      # 反转
    f3 = cross_sectional_zscore(-vol_20d, panel["date"])      # 低波
    f4 = cross_sectional_zscore(-turnover_5d, panel["date"])  # 低换手

    # ── 等权复合 ──
    composite = 0.25 * f1 + 0.25 * f2 + 0.25 * f3 + 0.25 * f4

    # 对齐回原始 panel 索引
    composite.index = panel.index
    return composite.reindex(panel.index)
