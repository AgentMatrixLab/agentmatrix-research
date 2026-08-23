from __future__ import annotations

import pandas as pd


def to_qlib_code(symbol: str) -> str:
    """Map SmartData symbol (000001.SZ) to qlib instrument code (SZ000001)."""
    code, exchange = symbol.split(".")
    prefix = {"SH": "SH", "SZ": "SZ", "BJ": "BJ"}.get(exchange.upper(), exchange.upper())
    return f"{prefix}{code}"


def from_qlib_code(code: str) -> str:
    """Map qlib instrument code (SH600000) to SmartData symbol (600000.SH)."""
    prefix = code[:2].upper()
    body = code[2:]
    exchange = {"SH": "SH", "SZ": "SZ", "BJ": "BJ"}.get(prefix, prefix)
    return f"{body}.{exchange}"


def apply_compute_universe_filters(panel: pd.DataFrame) -> pd.DataFrame:
    """Basic A-share hygiene for factor compute; does not intersect with qlib universe."""
    data = panel.copy()
    if "is_st" in data.columns:
        data = data[data["is_st"].fillna(0).astype(int) == 0]
    if "is_listed" in data.columns:
        data = data[data["is_listed"].fillna(1).astype(int) == 1]
    if "delist_date" in data.columns:
        data = data[data["delist_date"].isna() | (data["trade_date"] < data["delist_date"])]
    if "is_suspended" in data.columns:
        data = data[data["is_suspended"].fillna(0).astype(int) == 0]
    return data.reset_index(drop=True)


def apply_universe_filters(panel: pd.DataFrame, *, min_listed_days: int = 0) -> pd.DataFrame:
    """Backward-compatible alias; compute path no longer applies min_listed_days."""
    return apply_compute_universe_filters(panel)