"""
ClickHouse Data Bridge — connect agentmatrix-research to 115 ClickHouse.

Provides a unified interface for:
  - Fetching A-share OHLCV data from ClickHouse
  - Streaming factor computation results back
  - Caching queries for repeated access
"""

from __future__ import annotations

import os
import json
import time
from dataclasses import dataclass, field
from typing import Any

import pandas as pd


@dataclass(slots=True)
class ClickHouseConfig:
    """Connection config — ready for env vars or direct injection."""
    host: str = field(default_factory=lambda: os.environ.get("CLICKHOUSE_HOST", "115.159.73.134"))
    port: int = field(default_factory=lambda: int(os.environ.get("CLICKHOUSE_PORT", "8123")))
    user: str = field(default_factory=lambda: os.environ.get("CLICKHOUSE_USER", "default"))
    password: str = field(default_factory=lambda: os.environ.get("CLICKHOUSE_PASSWORD", ""))
    database: str = field(default_factory=lambda: os.environ.get("CLICKHOUSE_DB", "factor_db"))
    table: str = field(default_factory=lambda: os.environ.get("CLICKHOUSE_TABLE", "daily_kline"))
    timeout: int = 30
    max_retries: int = 3
    retry_delay: float = 2.0


class ClickHouseBridge:
    """Read-only ClickHouse connector for factor research.

    Usage:
        bridge = ClickHouseBridge(ClickHouseConfig(host="115.159.73.134"))
        df = bridge.fetch_kline(
            symbols=["000001.SZ", "000002.SZ"],
            start="2024-01-01",
            end="2024-12-31",
        )
    """

    def __init__(self, config: ClickHouseConfig | None = None):
        self.config = config or ClickHouseConfig()
        self._connected = False
        self._cache: dict[str, pd.DataFrame] = {}

    @property
    def base_url(self) -> str:
        return f"http://{self.config.host}:{self.config.port}"

    def _query(self, sql: str) -> pd.DataFrame:
        """Execute a ClickHouse SQL query via HTTP interface, returning a DataFrame."""
        import urllib.request
        import urllib.parse

        params = urllib.parse.urlencode({
            "query": sql,
            "user": self.config.user,
            "password": self.config.password,
            "database": self.config.database,
            "default_format": "JSONEachRow",
        })

        url = f"{self.base_url}/?{params}"
        last_error = None

        for attempt in range(self.config.max_retries):
            try:
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=self.config.timeout) as resp:
                    data = resp.read().decode("utf-8")
                if not data.strip():
                    return pd.DataFrame()
                rows = [json.loads(line) for line in data.strip().split("\n") if line.strip()]
                return pd.DataFrame(rows)
            except Exception as e:
                last_error = e
                if attempt < self.config.max_retries - 1:
                    time.sleep(self.config.retry_delay * (attempt + 1))

        raise ConnectionError(
            f"ClickHouse query failed after {self.config.max_retries} attempts: {last_error}"
        )

    def health_check(self) -> bool:
        """Test if ClickHouse is reachable and responding."""
        try:
            result = self._query("SELECT 1 AS ok")
            return not result.empty and result.iloc[0, 0] == 1
        except Exception:
            return False

    def fetch_kline(
        self,
        symbols: list[str] | None = None,
        start: str = "2020-01-01",
        end: str = "2024-12-31",
        fields: list[str] | None = None,
        limit: int = 10_000_000,
    ) -> pd.DataFrame:
        """Fetch daily K-line data from ClickHouse.

        Args:
            symbols: List of security codes (e.g. ['000001.SZ', '600000.SH']).
                     None = all symbols.
            start/end: Date range (YYYY-MM-DD).
            fields: Columns to fetch. Default: all OHLCV fields.
            limit: Max rows to return.

        Returns:
            DataFrame with standard columns: date, code, open, high, low, close, volume, amount.
        """
        if fields is None:
            fields = ["date", "code", "open", "high", "low", "close", "volume", "amount"]

        field_str = ", ".join(fields)
        conditions = [f"date >= '{start}'", f"date <= '{end}'"]

        if symbols:
            quoted = ", ".join(f"'{s}'" for s in symbols)
            conditions.append(f"code IN ({quoted})")

        where = " AND ".join(conditions)
        sql = f"SELECT {field_str} FROM {self.config.table} WHERE {where} ORDER BY date, code LIMIT {limit}"

        df = self._query(sql)

        # Standardize column types
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
        for col in ["open", "high", "low", "close", "volume", "amount"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        return df

    def fetch_factor_values(
        self,
        factor_name: str,
        symbols: list[str] | None = None,
        start: str = "2020-01-01",
        end: str = "2024-12-31",
    ) -> pd.DataFrame:
        """Fetch pre-computed factor values from ClickHouse.

        Args:
            factor_name: Factor name as stored in the factor_values table.
        """
        conditions = [
            f"factor_name = '{factor_name}'",
            f"date >= '{start}'",
            f"date <= '{end}'",
        ]
        if symbols:
            quoted = ", ".join(f"'{s}'" for s in symbols)
            conditions.append(f"code IN ({quoted})")

        where = " AND ".join(conditions)
        sql = f"SELECT date, code, factor_value FROM factor_values WHERE {where} ORDER BY date, code"

        df = self._query(sql)
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
        if "factor_value" in df.columns:
            df["factor_value"] = pd.to_numeric(df["factor_value"], errors="coerce")
        return df

    def list_factors(self) -> list[str]:
        """List all available factors in ClickHouse."""
        try:
            df = self._query("SELECT DISTINCT factor_name FROM factor_values ORDER BY factor_name")
            return df["factor_name"].tolist() if "factor_name" in df.columns else []
        except Exception:
            return []

    def list_tables(self) -> list[str]:
        """List available tables in the database."""
        try:
            df = self._query(f"SHOW TABLES FROM {self.config.database}")
            return df.iloc[:, 0].tolist() if not df.empty else []
        except Exception:
            return []

    def fetch_with_cache(
        self,
        cache_key: str,
        *,
        symbols: list[str] | None = None,
        start: str = "2020-01-01",
        end: str = "2024-12-31",
    ) -> pd.DataFrame:
        """Fetch kline data with in-memory caching."""
        if cache_key in self._cache:
            return self._cache[cache_key]
        df = self.fetch_kline(symbols=symbols, start=start, end=end)
        self._cache[cache_key] = df
        return df

    def close(self):
        """Clear cache (no persistent connection to close — HTTP is stateless)."""
        self._cache.clear()
        self._connected = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def get_default_bridge() -> ClickHouseBridge:
    """Factory: create bridge from environment variables or defaults."""
    return ClickHouseBridge()


__all__ = [
    "ClickHouseConfig",
    "ClickHouseBridge",
    "get_default_bridge",
]
