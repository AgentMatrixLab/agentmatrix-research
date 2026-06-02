# coding=utf-8
from __future__ import print_function, absolute_import, unicode_literals
from gm.api import *

import datetime
import os
import pandas as pd
import numpy as np

"""
示例策略仅供参考，不建议直接实盘使用。

小市值策略，等权买入全A市场中市值最小的前N只股票，月初调仓换股。
"""


def init(context):
    context.num = 10
    schedule(schedule_func=algo, date_rule='1d', time_rule='15:00:00')


def algo(context):
    now_str = context.now.strftime('%Y-%m-%d')
    last_date = get_previous_n_trading_dates(exchange='SHSE', date=now_str, n=1)[0]

    if context.now.month != pd.Timestamp(last_date).month:
        all_stock, all_stock_str = get_normal_stocks(now_str)
        fundamental = stk_get_daily_mktvalue_pt(
            symbols=all_stock,
            fields='tot_mv',
            trade_date=last_date,
            df=True,
        ).sort_values(by='tot_mv')
        to_buy = list(fundamental.iloc[:context.num, :]['symbol'])
        print('本次股票池有股票数目: ', len(to_buy))

        positions = get_position()
        for position in positions:
            symbol = position['symbol']
            if symbol not in to_buy:
                new_price = history_n(
                    symbol=symbol,
                    frequency='1d',
                    count=1,
                    end_time=now_str,
                    fields='close',
                    adjust=ADJUST_PREV,
                    adjust_end_time=context.backtest_end_time,
                    df=False,
                )[0]['close']
                order_target_percent(
                    symbol=symbol,
                    percent=0,
                    order_type=OrderType_Limit,
                    position_side=PositionSide_Long,
                    price=new_price,
                )

        percent = 0.98 / len(to_buy)
        for symbol in to_buy:
            new_price = history_n(
                symbol=symbol,
                frequency='1d',
                count=1,
                end_time=now_str,
                fields='close',
                adjust=ADJUST_PREV,
                adjust_end_time=context.backtest_end_time,
                df=False,
            )[0]['close']
            order_target_percent(
                symbol=symbol,
                percent=percent,
                order_type=OrderType_Limit,
                position_side=PositionSide_Long,
                price=new_price,
            )


def on_order_status(context, order):
    symbol = order['symbol']
    price = order['price']
    volume = order['volume']
    status = order['status']
    side = order['side']
    effect = order['position_effect']
    order_type = order['order_type']
    if status == 3:
        if effect == 1:
            side_effect = '开多仓' if side == 1 else '开空仓'
        else:
            side_effect = '平空仓' if side == 1 else '平多仓'
        order_type_word = '限价' if order_type == 1 else '市价'
        print('{}:标的：{}，操作：以{}{}，委托价格：{}，委托数量：{}'.format(
            context.now,
            symbol,
            order_type_word,
            side_effect,
            price,
            volume,
        ))


def get_normal_stocks(date, new_days=365, skip_suspended=True, skip_st=True):
    date = pd.Timestamp(date).replace(tzinfo=None)
    stocks_info = get_symbols(
        sec_type1=1010,
        sec_type2=101001,
        skip_suspended=skip_suspended,
        skip_st=skip_st,
        trade_date=date.strftime('%Y-%m-%d'),
        df=True,
    )
    stocks_info['listed_date'] = stocks_info['listed_date'].apply(lambda x: x.replace(tzinfo=None))
    stocks_info['delisted_date'] = stocks_info['delisted_date'].apply(lambda x: x.replace(tzinfo=None))
    stocks_info = stocks_info[
        (stocks_info['listed_date'] <= date - datetime.timedelta(days=new_days))
        & (stocks_info['delisted_date'] > date)
    ]
    all_stocks = list(stocks_info['symbol'])
    all_stocks_str = ','.join(all_stocks)
    return all_stocks, all_stocks_str


def on_backtest_finished(context, indicator):
    print('*' * 50)
    print('回测已完成，请通过右上角“回测历史”功能查询详情。')


if __name__ == '__main__':
    run(
        strategy_id=os.getenv('GM_SMALL_CAP_STRATEGY_ID', 'demo-gm-small-cap-monthly'),
        filename='gm_small_cap_monthly.py',
        mode=MODE_BACKTEST,
        token=os.getenv('GM_TOKEN', ''),
        backtest_start_time='2025-01-01 08:00:00',
        backtest_end_time='2026-03-18 16:00:00',
        backtest_adjust=ADJUST_PREV,
        backtest_initial_cash=1000000,
        backtest_commission_ratio=0.0001,
        backtest_slippage_ratio=0.0001,
        backtest_match_mode=1,
    )

