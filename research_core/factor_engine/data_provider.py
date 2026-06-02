from __future__ import annotations

import os
import time
from pathlib import Path

import numpy as np
import pandas as pd

from common.paths import data_path

_CACHE_DIR = data_path("market_data_cache")
_CACHE_DIR.mkdir(parents=True, exist_ok=True)

try:
    import akshare as ak
    _AKSHARE_AVAILABLE = True
except ImportError:
    _AKSHARE_AVAILABLE = False


def _check_akshare():
    if not _AKSHARE_AVAILABLE:
        raise ImportError("akshare is required for data fetching. Install with: pip install akshare")


class MarketDataProvider:
    def __init__(self, cache_dir: str | Path | None = None, cache_ttl_hours: int = 6):
        self.cache_dir = Path(cache_dir) if cache_dir else _CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_ttl = cache_ttl_hours * 3600
        self._stock_list_cache: pd.DataFrame | None = None

    def _cache_path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.parquet"

    def _read_cache(self, key: str) -> pd.DataFrame | None:
        path = self._cache_path(key)
        if not path.exists():
            return None
        mtime = path.stat().st_mtime
        if time.time() - mtime > self.cache_ttl:
            return None
        try:
            return pd.read_parquet(path)
        except Exception:
            return None

    def _write_cache(self, key: str, df: pd.DataFrame) -> None:
        path = self._cache_path(key)
        try:
            df.to_parquet(path, index=False)
        except Exception:
            pass

    def get_stock_list(self) -> pd.DataFrame:
        _check_akshare()
        if self._stock_list_cache is not None:
            return self._stock_list_cache

        cache_key = "stock_list"
        cached = self._read_cache(cache_key)
        if cached is not None:
            self._stock_list_cache = cached
            return cached

        df = ak.stock_zh_a_spot_em()
        df = df.rename(columns={
            "代码": "symbol", "名称": "name", "最新价": "close",
            "涨跌幅": "pct_change", "成交额": "amount",
            "换手率": "turnover", "市盈率-动态": "pe_ttm",
            "市净率": "pb", "总市值": "total_mv",
            "流通市值": "circ_mv", "成交量": "volume",
        })
        df = df[df["close"].notna()].copy()
        df["symbol"] = df["symbol"].astype(str)

        self._write_cache(cache_key, df)
        self._stock_list_cache = df
        return df

    def get_stock_daily(
        self,
        symbol: str,
        start_date: str = "20200101",
        end_date: str | None = None,
        adjust: str = "qfq",
    ) -> pd.DataFrame:
        _check_akshare()
        if end_date is None:
            end_date = pd.Timestamp.now().strftime("%Y%m%d")

        cache_key = f"daily_{symbol}_{start_date}_{end_date}_{adjust}"
        cached = self._read_cache(cache_key)
        if cached is not None:
            return cached

        try:
            df = ak.stock_zh_a_hist(
                symbol=symbol, period="daily",
                start_date=start_date, end_date=end_date,
                adjust=adjust,
            )
        except Exception as e:
            print(f"[DataProvider] Error fetching {symbol}: {e}")
            return pd.DataFrame()

        if df.empty:
            return df

        df = df.rename(columns={
            "日期": "date", "开盘": "open", "收盘": "close",
            "最高": "high", "最低": "low", "成交量": "volume",
            "成交额": "amount", "换手率": "turnover",
        })
        df["date"] = pd.to_datetime(df["date"])
        df["symbol"] = symbol
        df = df.sort_values("date").reset_index(drop=True)

        self._write_cache(cache_key, df)
        return df

    def get_index_daily(
        self,
        symbol: str = "sh000300",
        start_date: str = "20200101",
        end_date: str | None = None,
    ) -> pd.DataFrame:
        _check_akshare()
        if end_date is None:
            end_date = pd.Timestamp.now().strftime("%Y%m%d")

        cache_key = f"index_{symbol}_{start_date}_{end_date}"
        cached = self._read_cache(cache_key)
        if cached is not None:
            return cached

        try:
            df = ak.stock_zh_index_daily(symbol=symbol)
        except Exception:
            try:
                df = ak.index_zh_a_hist(
                    symbol=symbol.replace("sh", "").replace("sz", ""),
                    period="daily",
                    start_date=start_date,
                    end_date=end_date,
                )
            except Exception as e:
                print(f"[DataProvider] Error fetching index {symbol}: {e}")
                return pd.DataFrame()

        if df.empty:
            return df

        col_map = {
            "date": "date", "Date": "date",
            "close": "close", "Close": "close",
            "open": "open", "Open": "open",
            "high": "high", "High": "high",
            "low": "low", "Low": "low",
            "volume": "volume", "Volume": "volume",
        }
        df = df.rename(columns=col_map)
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)

        self._write_cache(cache_key, df)
        return df

    def get_stock_daily_batch(
        self,
        symbols: list[str],
        start_date: str = "20200101",
        end_date: str | None = None,
        adjust: str = "qfq",
    ) -> dict[str, pd.DataFrame]:
        results = {}
        for i, symbol in enumerate(symbols):
            df = self.get_stock_daily(symbol, start_date, end_date, adjust)
            if not df.empty:
                results[symbol] = df
            if (i + 1) % 50 == 0:
                print(f"[DataProvider] Fetched {i + 1}/{len(symbols)} stocks")
        return results

    def build_panel(
        self,
        symbols: list[str],
        start_date: str = "20200101",
        end_date: str | None = None,
        adjust: str = "qfq",
        fields: list[str] | None = None,
    ) -> pd.DataFrame:
        if fields is None:
            fields = ["open", "high", "low", "close", "volume", "amount", "turnover"]

        batch = self.get_stock_daily_batch(symbols, start_date, end_date, adjust)
        if not batch:
            return pd.DataFrame()

        panels = []
        for symbol, df in batch.items():
            cols = ["date", "symbol"] + [c for c in fields if c in df.columns]
            panels.append(df[cols].copy())

        panel = pd.concat(panels, ignore_index=True)
        panel = panel.sort_values(["date", "symbol"]).reset_index(drop=True)
        return panel

    def build_close_matrix(
        self,
        symbols: list[str],
        start_date: str = "20200101",
        end_date: str | None = None,
        adjust: str = "qfq",
    ) -> pd.DataFrame:
        batch = self.get_stock_daily_batch(symbols, start_date, end_date, adjust)
        if not batch:
            return pd.DataFrame()

        close_dict = {}
        for symbol, df in batch.items():
            if "close" in df.columns and "date" in df.columns:
                s = df.set_index("date")["close"]
                s.index = pd.to_datetime(s.index)
                close_dict[symbol] = s

        return pd.DataFrame(close_dict)
