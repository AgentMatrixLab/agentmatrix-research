# coding=utf-8
from __future__ import print_function, absolute_import, unicode_literals
from gm.api import *

import datetime
import os
import numpy as np
import pandas as pd

'''
示例策略仅供参考，不建议直接实盘使用。

风格轮动策略。
逻辑：以上证50、沪深300、中证500作为市场三个风格的代表，每次选取表现最好的一种风格，
买入其成分股中最大市值的 N 只股票，每月月初进行调仓换股。
'''


def init(context):
    context.index = ['SHSE.000016', 'SHSE.000300', 'SZSE.399625']
    context.days = 20
    context.holding_num = 10
    schedule(schedule_func=algo, date_rule='1d', time_rule='09:30:00')


def algo(context):
    now_str = context.now.strftime('%Y-%m-%d')
    last_day = get_previous_n_trading_dates(exchange='SHSE', date=now_str, n=1)[0]
    if context.now.month != pd.Timestamp(last_day).month:
        return_index = pd.DataFrame(columns=['return'])
        for index_symbol in context.index:
            return_index_his = history_n(
                symbol=index_symbol,
                frequency='1d',
                count=context.days + 1,
                fields='close,bob',
                fill_missing='Last',
                adjust=ADJUST_PREV,
                end_time=last_day,
                df=True,
            )
            close_values = return_index_his['close'].values
            return_index.loc[index_symbol, 'return'] = close_values[-1] / close_values[0] - 1

        sector = return_index.index[np.argmax(return_index)]
        print('{}:最佳指数是:{}'.format(now_str, sector))

        symbols = list(stk_get_index_constituents(index=sector, trade_date=last_day)['symbol'])
        stocks_info = get_symbols(
            sec_type1=1010,
            symbols=symbols,
            trade_date=now_str,
            skip_suspended=True,
            skip_st=True,
        )
        symbols = [
            item['symbol']
            for item in stocks_info
            if item['listed_date'] < context.now and item['delisted_date'] > context.now
        ]
        fin = stk_get_daily_mktvalue_pt(
            symbols=symbols,
            fields='tot_mv',
            trade_date=last_day,
            df=True,
        ).sort_values(by='tot_mv', ascending=False)
        to_buy = list(fin.iloc[:context.holding_num]['symbol'])

        percent = 0.98 / len(to_buy)
        positions = get_position()

        for position in positions:
            symbol = position['symbol']
            if symbol not in to_buy:
                new_price = history_n(
                    symbol=symbol,
                    frequency='1d',
                    count=1,
                    end_time=now_str,
                    fields='open',
                    adjust=ADJUST_PREV,
                    adjust_end_time=context.backtest_end_time,
                    df=False,
                )[0]['open']
                order_target_percent(
                    symbol=symbol,
                    percent=0,
                    order_type=OrderType_Limit,
                    position_side=PositionSide_Long,
                    price=new_price,
                )

        for symbol in to_buy:
            new_price = history_n(
                symbol=symbol,
                frequency='1d',
                count=1,
                end_time=now_str,
                fields='open',
                adjust=ADJUST_PREV,
                adjust_end_time=context.backtest_end_time,
                df=False,
            )[0]['open']
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


def on_backtest_finished(context, indicator):
    print('*' * 50)
    print('回测已完成，请通过右上角“回测历史”功能查询详情。')


if __name__ == '__main__':
    run(
        strategy_id=os.getenv('GM_STYLE_ROTATION_STRATEGY_ID', 'demo-gm-style-rotation'),
        filename='gm_style_rotation.py',
        mode=MODE_BACKTEST,
        token=os.getenv('GM_TOKEN', ''),
        backtest_start_time='2025-01-01 08:00:00',
        backtest_end_time='2025-12-31 16:00:00',
        backtest_adjust=ADJUST_PREV,
        backtest_initial_cash=10000000,
        backtest_commission_ratio=0.0001,
        backtest_slippage_ratio=0.0001,
        backtest_match_mode=1,
    )
