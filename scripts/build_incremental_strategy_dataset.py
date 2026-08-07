from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from research_core.strategy_operations.dataset_builder import (
    canonical_symbols, copy_base_files, finalize_manifest, merge_unique, normalize_dividend_yield,
    normalize_boolean_matrix, normalize_price_frames,
)


def initialize_rq(module_name: str | None) -> None:
    import rqdatac
    if module_name:
        if not getattr(importlib.import_module(module_name), "init_rq")():
            raise RuntimeError("RQData initializer returned false")
        return
    username, password = os.getenv("RQDATA_USERNAME"), os.getenv("RQDATA_PASSWORD")
    if not username or not password:
        raise RuntimeError("Set RQDATA_USERNAME and RQDATA_PASSWORD")
    rqdatac.init(username, password)


def interval_stocks(rqdatac, start: str, end: str) -> list[str]:
    instruments = rqdatac.all_instruments("CS", market="cn")
    listed = pd.to_datetime(instruments["listed_date"], errors="coerce")
    delisted = pd.to_datetime(instruments["de_listed_date"], errors="coerce")
    mask = (listed <= pd.Timestamp(end)) & (delisted.isna() | (delisted >= pd.Timestamp(start)))
    return sorted(instruments.loc[mask, "order_book_id"].astype(str).tolist())


def main() -> int:
    parser = argparse.ArgumentParser(description="Build an immutable daily custom-engine dataset")
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--reference-index", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--end", required=True)
    parser.add_argument("--initializer-module", default="")
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"output already exists: {args.output}")
    base_manifest = json.loads((args.base / "manifest.json").read_text(encoding="utf-8"))
    base_version = str(base_manifest.get("data_version") or base_manifest["details"]["kline_adj.parquet"]["date_max"])
    start = (pd.Timestamp(base_version) + pd.Timedelta(days=1)).date().isoformat()
    staging = args.output.with_name(f".{args.output.name}.building-{os.getpid()}")
    staging.mkdir(parents=True)
    copy_base_files(args.base, staging)
    for dividend_file in sorted(staging.glob("dividend_yield_*.parquet")):
        normalize_dividend_yield(pd.read_parquet(dividend_file)).to_parquet(
            dividend_file, index=False, compression="zstd"
        )
    initialize_rq(args.initializer_module or None)
    import rqdatac

    stocks = interval_stocks(rqdatac, start, args.end)
    fields = ["open", "high", "low", "close", "volume", "total_turnover", "limit_up", "limit_down"]
    raw = rqdatac.get_price(stocks, start, args.end, frequency="1d", fields=fields, adjust_type="none", skip_suspended=False, expect_df=True)
    adjusted = rqdatac.get_price(stocks, start, args.end, frequency="1d", fields=["open", "high", "low", "close"], adjust_type="pre", skip_suspended=False, expect_df=True)
    prices = normalize_price_frames(raw, adjusted)
    old_prices = pd.read_parquet(args.base / "kline_adj.parquet")
    all_prices = merge_unique(old_prices, prices, ["symbol", "trade_date"])
    all_prices.to_parquet(staging / "kline_adj.parquet", index=False, compression="zstd")

    suspended = normalize_boolean_matrix(rqdatac.is_suspended(stocks, start, args.end), "is_suspended")
    st = normalize_boolean_matrix(rqdatac.is_st_stock(stocks, start, args.end), "is_st")
    status_update = suspended.merge(st, on=["symbol", "trade_date"], how="outer").fillna(0)
    old_status = pd.read_parquet(args.base / "security_status.parquet")
    status = merge_unique(old_status, status_update, ["symbol", "trade_date"])
    status.to_parquet(staging / "security_status.parquet", index=False, compression="zstd")

    dividend = rqdatac.get_factor(stocks, factor="dividend_yield_ttm", start_date=start, end_date=args.end, expect_df=True).reset_index()
    dividend = normalize_dividend_yield(
        dividend.rename(columns={"order_book_id": "symbol", "dividend_yield_ttm": "dividend_yield"})
    )
    dividend_path = staging / f"dividend_yield_{pd.Timestamp(args.end).year}.parquet"
    existing_dividend = normalize_dividend_yield(pd.read_parquet(dividend_path)) if dividend_path.exists() else pd.DataFrame(columns=dividend.columns)
    merge_unique(existing_dividend, dividend, ["symbol", "date"]).to_parquet(dividend_path, index=False, compression="zstd")

    calendar = pd.DataFrame({"trade_date": sorted(all_prices["trade_date"].drop_duplicates())})
    calendar.to_parquet(staging / "calendar.parquet", index=False, compression="zstd")
    reference = pd.read_parquet(args.reference_index)
    reference = reference[reference["order_book_id"].isin(["000300.XSHG", "000300.SH"])][["date", "close"]].rename(columns={"close": "CSI300"}).sort_values("date")
    reference.to_parquet(staging / "csi300_index.parquet", index=False, compression="zstd")
    details = {
        "kline_adj.parquet": {"rows": len(all_prices), "date_min": all_prices["trade_date"].min().date().isoformat(), "date_max": all_prices["trade_date"].max().date().isoformat()},
        "security_status.parquet": {"rows": len(status), "date_max": status["trade_date"].max().date().isoformat()},
        "dividend_yield": {"factor": "dividend_yield_ttm", "unit": "decimal", "rows_added": len(dividend), "date_max": dividend["date"].max().date().isoformat()},
        "csi300_index.parquet": {"rows": len(reference), "date_max": pd.to_datetime(reference["date"]).max().date().isoformat()},
    }
    manifest = finalize_manifest(staging, data_version=args.end, base_version=base_version, details=details)
    staging.replace(args.output)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
