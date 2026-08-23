from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


def _canonical_symbol(series: pd.Series) -> pd.Series:
    return (
        series.astype(str)
        .str.replace(".XSHG", ".SH", regex=False)
        .str.replace(".XSHE", ".SZ", regex=False)
    )


def _write_kline(source: Path, output: Path, years: range) -> dict:
    writer: pq.ParquetWriter | None = None
    total_rows = 0
    date_min = None
    date_max = None
    try:
        for year in years:
            path = source / f"prices_{year}.parquet"
            if not path.is_file():
                continue
            frame = pd.read_parquet(path)
            normalized = pd.DataFrame(
                {
                    "symbol": _canonical_symbol(frame["code"]),
                    "trade_date": pd.to_datetime(frame["date"]),
                    "open": frame["raw_open"].astype("float64"),
                    "high": frame["raw_high"].astype("float64"),
                    "low": frame["raw_low"].astype("float64"),
                    "close": frame["raw_close"].astype("float64"),
                    "open_adj": frame["adjusted_open"].astype("float64"),
                    "high_adj": frame["adjusted_high"].astype("float64"),
                    "low_adj": frame["adjusted_low"].astype("float64"),
                    "close_adj": frame["adjusted_close"].astype("float64"),
                    "volume": frame["raw_volume"].astype("float64"),
                    "amount": frame["raw_total_turnover"].astype("float64"),
                    "limit_up": frame["raw_limit_up"].astype("float64"),
                    "limit_down": frame["raw_limit_down"].astype("float64"),
                }
            ).sort_values(["symbol", "trade_date"])
            table = pa.Table.from_pandas(normalized, preserve_index=False)
            if writer is None:
                writer = pq.ParquetWriter(output, table.schema, compression="zstd")
            writer.write_table(table, row_group_size=200_000)
            total_rows += len(normalized)
            current_min = normalized["trade_date"].min()
            current_max = normalized["trade_date"].max()
            date_min = current_min if date_min is None else min(date_min, current_min)
            date_max = current_max if date_max is None else max(date_max, current_max)
    finally:
        if writer is not None:
            writer.close()
    if total_rows == 0:
        raise FileNotFoundError(f"No prices_YYYY.parquet files found under {source}")
    return {
        "rows": total_rows,
        "date_min": str(date_min.date()),
        "date_max": str(date_max.date()),
    }


def _write_status(source: Path, output: Path, years: range) -> dict:
    parts = []
    for year in years:
        path = source / f"status_{year}.parquet"
        if not path.is_file():
            continue
        frame = pd.read_parquet(path)
        parts.append(
            pd.DataFrame(
                {
                    "symbol": _canonical_symbol(frame["code"]),
                    "trade_date": pd.to_datetime(frame["date"]),
                    "is_suspended": frame["is_suspended"].fillna(False).astype("int8"),
                    "is_st": frame["is_st"].fillna(False).astype("int8"),
                }
            )
        )
    if not parts:
        return {"rows": 0}
    result = pd.concat(parts, ignore_index=True).sort_values(["trade_date", "symbol"])
    result.to_parquet(output, index=False, compression="zstd")
    return {"rows": len(result)}


def _write_securities(source: Path, output: Path) -> dict:
    frame = pd.read_parquet(source)
    status = frame.get("status", pd.Series("Active", index=frame.index)).astype(str).str.lower()
    result = pd.DataFrame(
        {
            "symbol": _canonical_symbol(frame["order_book_id"]),
            "sec_name": frame.get("abbrev_symbol", frame["order_book_id"]).astype(str),
            "is_listed": (~status.isin({"delisted", "inactive"})).astype("int8"),
            "listed_date": pd.to_datetime(frame.get("listed_date"), errors="coerce"),
            "de_listed_date": pd.to_datetime(frame.get("de_listed_date"), errors="coerce"),
            "exchange": frame.get("exchange", "").astype(str),
            "board_type": frame.get("board_type", "").astype(str),
        }
    )
    result.to_parquet(output, index=False, compression="zstd")
    return {"rows": len(result)}


def _write_index(source: Path, output: Path) -> dict:
    frame = pd.read_parquet(source)
    if "order_book_id" not in frame.columns and "order_book_id" in frame.index.names:
        frame = frame.reset_index()
    target = frame[frame["order_book_id"].isin(["000300.XSHG", "000300.SH"])].copy()
    if target.empty:
        return {"rows": 0}
    result = pd.DataFrame(
        {"date": pd.to_datetime(target["date"]), "CSI300": target["close"].astype("float64")}
    ).sort_values("date")
    result.to_parquet(output, index=False, compression="zstd")
    return {"rows": len(result)}


def _write_calendar(source: Path, output: Path) -> dict:
    frame = pd.read_parquet(source)
    if "trade_date" not in frame.columns:
        if "date" not in frame.columns:
            raise KeyError("Calendar requires date or trade_date")
        frame = frame.rename(columns={"date": "trade_date"})
    result = frame[["trade_date"]].copy()
    result["trade_date"] = pd.to_datetime(result["trade_date"])
    result = result.drop_duplicates().sort_values("trade_date")
    result.to_parquet(output, index=False, compression="zstd")
    return {"rows": len(result)}


def _copy_financial(source: Path, output: Path) -> dict:
    frame = pd.read_parquet(source)
    frame["symbol"] = _canonical_symbol(frame["symbol"])
    frame["ann_date"] = pd.to_datetime(frame["ann_date"])
    frame.to_parquet(output, index=False, compression="zstd")
    return {"rows": len(frame)}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare the legacy custom-engine Parquet dataset")
    parser.add_argument("--amr-source", required=True, type=Path)
    parser.add_argument("--financial-source", required=True, type=Path)
    parser.add_argument("--dividend-source", required=True, type=Path)
    parser.add_argument("--index-source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--start-year", type=int, default=2020)
    parser.add_argument("--end-year", type=int, default=2026)
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    years = range(args.start_year, args.end_year + 1)
    details = {}
    details["kline_adj.parquet"] = _write_kline(args.amr_source, args.output / "kline_adj.parquet", years)
    details["security_status.parquet"] = _write_status(
        args.amr_source, args.output / "security_status.parquet", years
    )
    details["stock_info.parquet"] = _write_securities(
        args.amr_source / "securities.parquet", args.output / "stock_info.parquet"
    )
    details["balance_sheet.parquet"] = _copy_financial(
        args.financial_source / "balance_sheet_new.parquet", args.output / "balance_sheet.parquet"
    )
    details["income_stmt.parquet"] = _copy_financial(
        args.financial_source / "income_stmt_new.parquet", args.output / "income_stmt.parquet"
    )
    details["csi300_index.parquet"] = _write_index(
        args.index_source / "index_daily.parquet", args.output / "csi300_index.parquet"
    )
    details["calendar.parquet"] = _write_calendar(
        args.amr_source / "calendar.parquet", args.output / "calendar.parquet"
    )

    for source in sorted(args.dividend_source.glob("dividend_yield_*.parquet")):
        year_text = source.stem.rsplit("_", 1)[-1]
        if year_text.isdigit() and args.start_year <= int(year_text) <= args.end_year:
            shutil.copy2(source, args.output / source.name)

    manifest_files = {}
    for path in sorted(args.output.glob("*.parquet")):
        parquet_file = pq.ParquetFile(path)
        manifest_files[path.name] = {
            "bytes": path.stat().st_size,
            "rows": parquet_file.metadata.num_rows,
            "sha256": _sha256(path),
            "columns": parquet_file.schema.names,
        }
    manifest = {
        "schema_version": "agentmatrix_custom_engine_dataset_v1",
        "start_year": args.start_year,
        "end_year": args.end_year,
        "details": details,
        "files": manifest_files,
    }
    (args.output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
