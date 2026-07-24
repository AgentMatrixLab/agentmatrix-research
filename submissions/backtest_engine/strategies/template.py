"""
策略模板 — 复制这个文件, 改 get_signals 函数即可

你的策略只需要实现一个函数:

def get_signals(data):
    ...
    return signals

- data: DataFrame, 包含:
    symbol       股票代码 (如 "000001.SZ")
    trade_date   交易日期
    open/close/high/low/volume  行情
    close_adj   后复权收盘价
    ret_1d, ret_5d, ret_10d, ret_20d, ret_60d  收益率
    ma_5, ma_10, ma_20, ma_60  移动平均
    volatility_20d  波动率
    is_suspended  是否停牌 (0/1)
    st_status     ST状态 (空字符串=正常)

- signals: DataFrame, 必须包含两列:
    symbol  : 股票代码
    weight  : 目标权重 (比例, 1=满仓一只)

提示:
- weight 的和不需要等于1, 框架会自动归一化
- 返回前50只即可 (超过配置的 MAX_STOCKS 会自动截断)
- 所有股票都在 data 里, 不需要额外过滤ST/停牌 (框架已经过滤)
"""
STRATEGY_NAME = "模板策略"

import pandas as pd
import numpy as np


def get_signals(data):
    """
    data: 当天的横截面数据 (所有可交易股票)
    """
    # ====== 你的因子计算逻辑写在这里 ======
    # 示例: ROE * 0.3 + 动量 * 0.7 (使用预计算因子)
    # data['score'] = data['pe_ttm'].fillna(0).rank() * 0.5 + ...

    # 简单示例: 用5日反转做信号 (过去5天跌得多的股票)
    data = data.copy()
    data['score'] = -data['ret_5d'].fillna(0)  # 跌越多得分越高

    # 选分最高的50只
    top = data.nlargest(50, 'score')

    signals = pd.DataFrame({
        'symbol': top['symbol'].values,
        'weight': 1.0 / len(top)  # 等权
    })

    return signals
