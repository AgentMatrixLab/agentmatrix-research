from __future__ import annotations

from rqalpha.apis import history_bars, order_target_percent

__config__ = {
    "base": {
        "start_date": "2023-01-01",
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
    context.short_window = 5
    context.long_window = 20
    context.last_signal = "flat"



def handle_bar(context, bar_dict):
    closes = history_bars(context.target, context.long_window, "1d", "close")
    if closes is None or len(closes) < context.long_window:
        return

    short_ma = float(closes[-context.short_window:].mean())
    long_ma = float(closes.mean())

    if short_ma > long_ma and context.last_signal != "long":
        order_target_percent(context.target, 0.95)
        context.last_signal = "long"
    elif short_ma < long_ma and context.last_signal != "flat":
        order_target_percent(context.target, 0)
        context.last_signal = "flat"
