"""
示例策略 — 动量因子 + 低波因子双因子打分

策略逻辑:
  momentum_60d (60日动量) × 0.6 + volatility_20d_reverse (低波) × 0.4
  选得分最高的50只, 等权持仓
"""
STRATEGY_NAME = "动量+低波"

import pandas as pd
import numpy as np


def get_signals(data):
    data = data.copy()

    # 60日动量 (越大越好)
    data['momentum'] = data['ret_60d'].fillna(0)

    # 20日波动率 (越小越好, 取倒数)
    data['low_vol'] = 1 / (data['volatility_20d'].fillna(data['volatility_20d'].median()) + 0.001)

    # 综合打分
    data['score'] = data['momentum'].rank(pct=True) * 0.6 + data['low_vol'].rank(pct=True) * 0.4

    # 选前50
    top = data.nlargest(50, 'score')

    return pd.DataFrame({
        'symbol': top['symbol'].values,
        'weight': 1.0 / len(top)
    })
