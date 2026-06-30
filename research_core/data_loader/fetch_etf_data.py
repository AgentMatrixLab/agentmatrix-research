from __future__ import annotations

import pandas as pd
import akshare as ak


def fetch_dynamic_etf_pool() -> pd.DataFrame:
    etf_list = ak.fund_etf_category(symbol="ETF基金")
    etf_list = etf_list[["基金代码", "基金简称", "跟踪指数"]].copy()
    etf_list.columns = ["symbol", "name", "tracking_index"]
    return etf_list.dropna()


def fetch_etf_history_data(
    symbol: str,
    start_date: str | None = None,
    end_date: str | None = None,
    adjust: str = "hfq",
) -> pd.DataFrame:
    try:
        df = ak.fund_etf_hist(symbol=symbol, adjust=adjust)
        if start_date:
            df = df[df["日期"] >= start_date]
        if end_date:
            df = df[df["日期"] <= end_date]
        df = df.rename(columns={
            "日期": "date",
            "开盘": "open",
            "最高": "high",
            "最低": "low",
            "收盘": "close",
            "成交量": "volume",
            "成交额": "amount",
        })
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)
        return df
    except Exception as e:
        print(f"Failed to fetch ETF data for {symbol}: {e}")
        return pd.DataFrame()


def fetch_hs300_index_history(
    start_date: str | None = None,
    end_date: str | None = None,
) -> pd.DataFrame:
    df = ak.stock_zh_index_daily(symbol="sh000300")
    df = df.rename(columns={
        "日期": "date",
        "开盘": "open",
        "最高": "high",
        "最低": "low",
        "收盘": "close",
        "成交量": "volume",
        "成交额": "amount",
    })
    df["date"] = pd.to_datetime(df["date"])
    if start_date:
        df = df[df["date"] >= start_date]
    if end_date:
        df = df[df["date"] <= end_date]
    return df.sort_values("date").reset_index(drop=True)


def fetch_realtime_etf_prices_sina