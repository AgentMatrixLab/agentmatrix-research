from __future__ import annotations

from collections.abc import Iterable
from importlib import import_module

import pandas as pd


def _akshare():
    try:
        return import_module("akshare")
    except ImportError as exc:
        raise RuntimeError("akshare is required for ETF data fetching") from exc


def fetch_dynamic_etf_pool() -> pd.DataFrame:
    ak = _akshare()
    etf_list = ak.fund_etf_category(symbol="ETF基金")
    columns = ["基金代码", "基金简称", "跟踪指数"]
    available = [column for column in columns if column in etf_list.columns]
    if len(available) != len(columns):
        return pd.DataFrame(columns=["symbol", "name", "tracking_index"])
    etf_list = etf_list[columns].copy()
    etf_list.columns = ["symbol", "name", "tracking_index"]
    return etf_list.dropna()


def fetch_etf_history_data(
    symbol: str,
    start_date: str | None = None,
    end_date: str | None = None,
    adjust: str = "hfq",
) -> pd.DataFrame:
    ak = _akshare()
    try:
        df = ak.fund_etf_hist(symbol=symbol, adjust=adjust)
        df = df.rename(
            columns={
                "日期": "date",
                "开盘": "open",
                "最高": "high",
                "最低": "low",
                "收盘": "close",
                "成交量": "volume",
                "成交额": "amount",
            }
        )
        if "date" not in df.columns:
            return pd.DataFrame()
        df["date"] = pd.to_datetime(df["date"])
        if start_date:
            df = df[df["date"] >= pd.to_datetime(start_date)]
        if end_date:
            df = df[df["date"] <= pd.to_datetime(end_date)]
        return df.sort_values("date").reset_index(drop=True)
    except Exception as exc:
        print(f"Failed to fetch ETF data for {symbol}: {exc}")
        return pd.DataFrame()


def fetch_hs300_index_history(
    start_date: str | None = None,
    end_date: str | None = None,
) -> pd.DataFrame:
    ak = _akshare()
    df = ak.stock_zh_index_daily(symbol="sh000300")
    df = df.rename(
        columns={
            "日期": "date",
            "开盘": "open",
            "最高": "high",
            "最低": "low",
            "收盘": "close",
            "成交量": "volume",
            "成交额": "amount",
        }
    )
    df["date"] = pd.to_datetime(df["date"])
    if start_date:
        df = df[df["date"] >= pd.to_datetime(start_date)]
    if end_date:
        df = df[df["date"] <= pd.to_datetime(end_date)]
    return df.sort_values("date").reset_index(drop=True)


def fetch_realtime_etf_prices_sina(symbols: Iterable[str] | None = None) -> pd.DataFrame:
    ak = _akshare()
    df = ak.fund_etf_spot_em()
    df = df.rename(
        columns={
            "代码": "symbol",
            "名称": "name",
            "最新价": "price",
            "涨跌幅": "pct_change",
            "成交额": "amount",
        }
    )
    if symbols:
        wanted = {symbol for symbol in symbols}
        df = df[df["symbol"].isin(wanted)]
    keep_columns = [column for column in ["symbol", "name", "price", "pct_change", "amount"] if column in df.columns]
    return df[keep_columns].reset_index(drop=True)
