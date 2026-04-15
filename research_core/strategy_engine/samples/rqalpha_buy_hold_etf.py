from __future__ import annotations

from rqalpha.apis import order_value

__config__ = {
    "base": {
        "start_date": "2024-01-01",
        "end_date": "2024-12-31",
        "benchmark": "000300.XSHG",
        "accounts": {
            "stock": 1000000,
        },
    },
    "extra": {
        "log_level": "error",
    },
}


def init(context):
    context.target = "510300.XSHG"
    context.invested = False



def handle_bar(context, bar_dict):
    if context.invested:
        return
    cash = float(context.portfolio.cash)
    if cash <= 0:
        return
    order_value(context.target, cash * 0.95)
    context.invested = True
