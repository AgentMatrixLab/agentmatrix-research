"""Daily market data store for the AGE-8 daily-update pipeline.

Architecture decision (2026-08-12, CEO Jarvis):
- v1 storage: local DuckDB (``data/daily_store/market.duckdb``) + parquet panel
  snapshot. Self-contained, no external service dependency.
- Production path (Ada): SmartData ClickHouse (115.159.73.134) per M1; the
  DailyStore interface is the seam — swap the backend without touching callers.
"""

from __future__ import annotations

from datetime import date as date_cls
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from common.paths import data_path

STORE_DIR = data_path("daily_store")
DB_PATH = STORE_DIR / "market.duckdb"
PANEL_PATH = STORE_DIR / "market_panel.parquet"
TABLE = "daily_kline"


def _now_iso() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


class DailyStore:
    """DuckDB-backed OHLCV store keyed by (code, date)."""

    def __init__(self, db_path: Path | str = DB_PATH) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: duckdb.DuckDBPyConnection | None = None

    # -- connection -------------------------------------------------------
    def connect(self) -> duckdb.DuckDBPyConnection:
        if self._conn is None:
            self._conn = duckdb.connect(str(self.db_path))
            self._init_schema()
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def _init_schema(self) -> None:
        c = self.connect()
        c.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {TABLE} (
                code   VARCHAR,
                date   DATE,
                open   DOUBLE,
                high   DOUBLE,
                low    DOUBLE,
                close  DOUBLE,
                volume DOUBLE,
                amount DOUBLE,
                PRIMARY KEY (code, date)
            )
            """
        )

    # -- writes -----------------------------------------------------------
    def upsert(self, frame: pd.DataFrame) -> int:
        """Upsert a normalized frame [code, date, open, high, low, close, volume, amount]."""
        if frame.empty:
            return 0
        c = self.connect()
        c.execute(f"INSERT OR REPLACE INTO {TABLE} SELECT * FROM frame")
        return len(frame)

    # -- reads ------------------------------------------------------------
    def last_date(self) -> date_cls | None:
        c = self.connect()
        row = c.execute(f"SELECT max(date) FROM {TABLE}").fetchone()
        return row[0] if row and row[0] else None

    def row_count(self) -> int:
        c = self.connect()
        return int(c.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0])

    def code_count(self) -> int:
        c = self.connect()
        return int(c.execute(f"SELECT count(DISTINCT code) FROM {TABLE}").fetchone()[0])

    def load_panel(
        self,
        start: str | None = None,
        end: str | None = None,
    ) -> pd.DataFrame:
        """Load a qlib/SmartData-aligned panel [code, date, open, high, low, close, volume, amount, vwap]."""
        c = self.connect()
        sql = f"SELECT code, date, open, high, low, close, volume, amount FROM {TABLE}"
        where: list[str] = []
        if start:
            where.append(f"date >= DATE '{start}'")
        if end:
            where.append(f"date <= DATE '{end}'")
        if where:
            sql += " WHERE " + " AND ".join(where)
        df = c.execute(sql).fetch_df()
        if df.empty:
            return df
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values(["code", "date"]).reset_index(drop=True)
        df["vwap"] = df["amount"] / df["volume"].replace(0, pd.NA)
        return df

    def coverage_report(self, universe: list[str]) -> dict[str, Any]:
        """QC: per-universe coverage, freshness, and row sanity."""
        c = self.connect()
        total = self.row_count()
        codes = self.code_count()
        last = self.last_date()
        missing = [s for s in universe if not c.execute(
            f"SELECT 1 FROM {TABLE} WHERE code = ? LIMIT 1", [s]
        ).fetchone()]
        return {
            "rows": total,
            "codes": codes,
            "universe_size": len(universe),
            "coverage_codes": codes / max(len(universe), 1),
            "last_date": str(last) if last else None,
            "missing_codes": missing[:20],
            "missing_count": len(missing),
            "as_of": _now_iso(),
        }
