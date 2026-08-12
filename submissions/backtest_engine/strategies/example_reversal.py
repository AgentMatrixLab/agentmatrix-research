"""
示例策略 — 反转因子 (5日反转)
  做多过去5天跌得最惨的50只, 做空过去5天涨得最好的50只
  这里只做多 (A股散户不能做空实盘)
"""
STRATEGY_NAME = "5日反转"

import pandas as pd
import numpy as np


def get_signals(data):
    data = data.copy()

    # 5日收益 (越小=跌得越惨, 预期反弹)
    data['score'] = -data['ret_5d'].fillna(0)  # 取负: 跌得多的得分高

    # 选前50
    top = data.nlargest(50, 'score')

    return pd.DataFrame({
        'symbol': top['symbol'].values,
        'weight': 1.0 / len(top)
    })
