from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq


def canonical_symbols(series: pd.Series) -> pd.Series:
    return series.astype(str).str.replace(".XSHG", ".SH", regex=False).str.replace(".XSHE", ".SZ", regex=False)


def normalize_price_frames(raw: pd.DataFrame, adjusted: pd.DataFrame) -> pd.DataFrame:
    raw = raw.reset_index() if not {"order_book_id", "date"}.issubset(raw.columns) else raw.copy()
    adjusted = adjusted.reset_index() if not {"order_book_id", "date"}.issubset(adjusted.columns) else adjusted.copy()
    keys = ["order_book_id", "date"]
    adjusted = adjusted[keys + ["open", "high", "low", "close"]].rename(
        columns={name: f"{name}_adj" for name in ("open", "high", "low", "close")}
    )
    result = raw.merge(adjusted, on=keys, how="inner", validate="one_to_one")
    result = result.rename(columns={"order_book_id": "symbol", "date": "trade_date", "total_turnover": "amount"})
    result["symbol"] = canonical_symbols(result["symbol"])
    result["trade_date"] = pd.to_datetime(result["trade_date"])
    columns = ["symbol", "trade_date", "open", "high", "low", "close", "open_adj", "high_adj", "low_adj", "close_adj", "volume", "amount", "limit_up", "limit_down"]
    return result[columns].sort_values(["symbol", "trade_date"])


def normalize_boolean_matrix(frame: pd.DataFrame, value_name: str) -> pd.DataFrame:
    wide = frame.copy()
    if wide.index.name is None:
        wide.index.name = "trade_date"
    long = wide.rename_axis("trade_date").reset_index().melt(
        id_vars=["trade_date"], var_name="symbol", value_name=value_name
    )
    long["symbol"] = canonical_symbols(long["symbol"])
    long["trade_date"] = pd.to_datetime(long["trade_date"])
    long[value_name] = long[value_name].fillna(False).astype("int8")
    return long


def merge_unique(existing: pd.DataFrame, update: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    return pd.concat([existing, update], ignore_index=True).drop_duplicates(keys, keep="last").sort_values(keys)


def normalize_dividend_yield(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    if "symbol" not in result.columns and "order_book_id" in result.columns:
        result = result.rename(columns={"order_book_id": "symbol"})
    if "dividend_yield" not in result.columns and "div_yield" in result.columns:
        result = result.rename(columns={"div_yield": "dividend_yield"})
    required = {"symbol", "date", "dividend_yield"}
    if not required.issubset(result.columns):
        raise ValueError(f"dividend yield data missing columns: {sorted(required - set(result.columns))}")
    result = result[["symbol", "date", "dividend_yield"]].copy()
    result["symbol"] = canonical_symbols(result["symbol"])
    result["date"] = pd.to_datetime(result["date"])
    result["dividend_yield"] = pd.to_numeric(result["dividend_yield"], errors="coerce")
    # RQData's legacy `dividend_yield` is expressed in basis points (398.2 = 3.982%).
    # The current `dividend_yield_ttm` factor is already a decimal (0.03982).
    median = result["dividend_yield"].abs().median(skipna=True)
    if pd.notna(median) and median > 1:
        result["dividend_yield"] /= 10_000.0
    return result.sort_values(["symbol", "date"])


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def finalize_manifest(root: Path, *, data_version: str, base_version: str, details: dict[str, Any]) -> dict[str, Any]:
    files = {}
    for path in sorted(root.glob("*.parquet")):
        files[path.name] = {"bytes": path.stat().st_size, "rows": pq.ParquetFile(path).metadata.num_rows, "sha256": sha256(path), "columns": pq.ParquetFile(path).schema.names}
    manifest = {"schema_version": "agentmatrix_custom_engine_dataset_v2", "data_version": data_version, "base_version": base_version, "details": details, "files": files}
    (root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def copy_base_files(base: Path, staging: Path) -> None:
    replaced = {"kline_adj.parquet", "security_status.parquet", "calendar.parquet", "csi300_index.parquet", "manifest.json"}
    for path in base.iterdir():
        if path.is_file() and path.name not in replaced:
            shutil.copy2(path, staging / path.name)
