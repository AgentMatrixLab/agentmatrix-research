"""AkShare/Tencent market data fetcher for the AGE-8 daily-update pipeline.

v1 sources (2026-08-12 verified on this host):
- Universe: CSI300 constituents via ``ak.index_stock_cons_csindex`` (fast, fresh).
- OHLCV: ``ak.stock_zh_a_hist_tx`` (Tencent) — eastmoney per-symbol endpoint is
  blocked from this host; Tencent verified working with qfq adjust.
"""

from __future__ import annotations

import time
from datetime import date as date_cls
from datetime import datetime, timedelta
from typing import Any, Callable

import akshare as ak
import pandas as pd

from research_core.daily_automation.store import DailyStore

_COL_MAP = {
    "日期": "date",
    "date": "date",
    "开盘": "open",
    "open": "open",
    "收盘": "close",
    "close": "close",
    "最高": "high",
    "high": "high",
    "最低": "low",
    "low": "low",
    "成交量": "volume",
    "volume": "volume",
    "成交额": "amount",
    "amount": "amount",
}

# Chinese A-share: 6xx -> Shanghai, 0/3xx -> Shenzhen, 4/8/9x -> Beijing
def _exchange_prefix(code: str) -> str:
    if code.startswith("6"):
        return "sh"
    if code.startswith(("0", "3")):
        return "sz"
    return "bj"


def fetch_constituents(index: str = "000300") -> list[str]:
    """CSI300 constituent codes (6-digit, without exchange suffix)."""
    df = ak.index_stock_cons_csindex(symbol=index)
    codes = [str(c).zfill(6) for c in df["成分券代码"].tolist()]
    return sorted(set(codes))


def fetch_daily_history(
    code: str,
    start: str,
    end: str,
    adjust: str = "qfq",
    retries: int = 3,
) -> pd.DataFrame:
    """Daily OHLCV for one code via Tencent. Returns normalized frame or empty."""
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            df = ak.stock_zh_a_hist_tx(
                symbol=f"{_exchange_prefix(code)}{code}",
                start_date=start,
                end_date=end,
                adjust=adjust,
            )
            if df is None or df.empty:
                return pd.DataFrame()
            df = df.rename(columns=_COL_MAP)
            df = df[["date", "open", "high", "low", "close", "volume", "amount"]].copy()
            df["date"] = pd.to_datetime(df["date"]).dt.date
            df["code"] = code
            for col in ("open", "high", "low", "close", "volume", "amount"):
                df[col] = pd.to_numeric(df[col], errors="coerce")
            df = df.dropna(subset=["close", "open"]).drop_duplicates(subset=["date"])
            return df[["code", "date", "open", "high", "low", "close", "volume", "amount"]]
        except Exception as exc:  # noqa: BLE001 — network flake, retry
            last_err = exc
            time.sleep(1.2 * (attempt + 1))
    print(f"  [warn] {code}: fetch failed after {retries} tries: {last_err!r}")
    return pd.DataFrame()


def update_universe(
    codes: list[str],
    start: str,
    end: str,
    store: DailyStore,
    *,
    pause: float = 0.2,
    on_progress: Callable[[int, int], None] | None = None,
    max_codes: int | None = None,
) -> dict[str, Any]:
    """Fetch and upsert history for the universe. Returns run summary."""
    if max_codes:
        codes = codes[:max_codes]
    ok, failed, rows = 0, 0, 0
    started = datetime.utcnow()
    for i, code in enumerate(codes, 1):
        frame = fetch_daily_history(code, start, end)
        if frame.empty:
            failed += 1
        else:
            rows += store.upsert(frame)
            ok += 1
        if on_progress:
            on_progress(i, len(codes))
        time.sleep(pause)
    elapsed_s = (datetime.utcnow() - started).total_seconds()
    return {
        "attempted": len(codes),
        "ok": ok,
        "failed": failed,
        "rows_upserted": rows,
        "elapsed_s": round(elapsed_s, 1),
        "window": {"start": start, "end": end},
        "as_of": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def default_window(days: int = 90) -> tuple[str, str]:
    end = date_cls.today()
    start = end - timedelta(days=int(days * 1.6))
    return start.strftime("%Y%m%d"), end.strftime("%Y%m%d")
