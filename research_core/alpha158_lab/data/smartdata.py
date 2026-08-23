from __future__ import annotations

from typing import Any

import pandas as pd
from clickhouse_driver import Client

from research_core.alpha158_lab.config import SmartDataConfig
from research_core.alpha158_lab.data.universe import apply_compute_universe_filters, to_qlib_code


def get_smartdata_client(config: SmartDataConfig | None = None) -> Client:
    cfg = config or SmartDataConfig.from_env()
    return Client(
        host=cfg.host,
        port=cfg.port,
        user=cfg.user,
        password=cfg.password,
        database=cfg.database,
    )


def _fetch_frame(client: Client, query: str) -> pd.DataFrame:
    rows, columns = client.execute(query, with_column_types=True)
    names = [name for name, _ in columns]
    return pd.DataFrame(rows, columns=names)


def fetch_trade_date_bounds(
    *,
    start_date: str = "2020-01-01",
    end_date: str = "2026-12-31",
    config: SmartDataConfig | None = None,
) -> tuple[str, str]:
    """Return the actual min/max trade_date available in ods_kline_1d for the window."""
    client = get_smartdata_client(config)
    row = client.execute(
        f"""
        SELECT min(trade_date), max(trade_date)
        FROM ods_kline_1d
        WHERE trade_date >= toDate('{start_date}')
          AND trade_date <= toDate('{end_date}')
        """
    )[0]
    if row[0] is None or row[1] is None:
        raise RuntimeError(f"No SmartData trade dates for {start_date} ~ {end_date}")
    return str(row[0]), str(row[1])


def load_market_panel(
    *,
    start_date: str,
    end_date: str,
    config: SmartDataConfig | None = None,
) -> pd.DataFrame:
    client = get_smartdata_client(config)
    query = f"""
    SELECT
        k.symbol AS symbol,
        k.trade_date AS trade_date,
        k.open AS open,
        k.high AS high,
        k.low AS low,
        k.close AS close,
        k.volume AS volume,
        k.amount AS amount,
        s.is_st AS is_st,
        s.is_suspended AS is_suspended,
        r.list_date AS list_date,
        r.delist_date AS delist_date,
        r.is_listed AS is_listed
    FROM ods_kline_1d AS k
    LEFT JOIN ods_security_status_daily AS s
        ON k.symbol = s.symbol AND k.trade_date = s.trade_date
    LEFT JOIN ref_security AS r
        ON k.symbol = r.symbol
    WHERE k.trade_date >= toDate('{start_date}')
      AND k.trade_date <= toDate('{end_date}')
    ORDER BY k.symbol, k.trade_date
    """
    raw = _fetch_frame(client, query)
    if raw.empty:
        raise RuntimeError(f"No SmartData rows for {start_date} ~ {end_date}")

    raw["trade_date"] = pd.to_datetime(raw["trade_date"])
    raw["list_date"] = pd.to_datetime(raw["list_date"], errors="coerce")
    raw["delist_date"] = pd.to_datetime(raw["delist_date"], errors="coerce")
    filtered = apply_compute_universe_filters(raw)
    filtered["code"] = filtered["symbol"].map(to_qlib_code)
    filtered["date"] = filtered["trade_date"]
    filtered["vwap"] = filtered["amount"] / filtered["volume"].replace(0, pd.NA)
    return filtered[["date", "code", "symbol", "open", "high", "low", "close", "volume", "amount", "vwap"]].copy()


def save_panel(panel: pd.DataFrame, path: str) -> dict[str, Any]:
    output = pd.DataFrame(panel)
    output.to_parquet(path, index=False)
    return {
        "path": path,
        "rows": int(len(output)),
        "codes": int(output["code"].nunique()),
        "date_min": str(output["date"].min()),
        "date_max": str(output["date"].max()),
    }