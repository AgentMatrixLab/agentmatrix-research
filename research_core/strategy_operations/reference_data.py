from __future__ import annotations

from pathlib import Path

import pandas as pd


INDEX_COLUMNS = ["order_book_id", "date", "open", "high", "low", "close", "volume", "total_turnover"]


def normalize_index_frame(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for name in ("order_book_id", "date"):
        if name not in result.columns and name in result.index.names:
            result = result.reset_index(level=name)
    missing = set(INDEX_COLUMNS) - set(result.columns)
    if missing:
        raise ValueError(f"index data missing columns: {sorted(missing)}")
    result = result[INDEX_COLUMNS].copy()
    result["date"] = pd.to_datetime(result["date"])
    return result.sort_values(["order_book_id", "date"])


def merge_index_data(existing: pd.DataFrame, update: pd.DataFrame) -> pd.DataFrame:
    combined = pd.concat([normalize_index_frame(existing), normalize_index_frame(update)], ignore_index=True)
    return combined.drop_duplicates(["order_book_id", "date"], keep="last").sort_values(["order_book_id", "date"])


def write_index_data(existing_path: Path, output_path: Path, update: pd.DataFrame) -> dict:
    existing = pd.read_parquet(existing_path)
    combined = merge_index_data(existing, update)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    combined.to_parquet(temporary, index=False, compression="zstd")
    temporary.replace(output_path)
    target = combined[combined["order_book_id"].isin(["000300.XSHG", "000300.SH"])]
    return {"rows": len(combined), "csi300_rows": len(target), "date_max": target["date"].max().date().isoformat()}
