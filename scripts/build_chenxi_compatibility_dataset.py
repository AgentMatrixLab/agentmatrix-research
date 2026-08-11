from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from research_core.strategy_operations.dataset_builder import finalize_manifest


def _add_signal_features(staging: Path, details: dict) -> None:
    path = staging / "kline_adj.parquet"
    if not path.exists():
        return
    frame = pd.read_parquet(path)
    price_column = "close_adj" if "close_adj" in frame.columns else "close"
    required = {"symbol", "trade_date", price_column}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"kline_adj.parquet missing columns: {sorted(missing)}")

    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    frame = frame.sort_values(["symbol", "trade_date"])
    grouped_price = frame.groupby("symbol", sort=False)[price_column]
    frame["ret_5d"] = grouped_price.pct_change(5, fill_method=None)
    frame["ret_60d"] = grouped_price.pct_change(60, fill_method=None)
    frame["ret_1d"] = grouped_price.pct_change(fill_method=None)
    frame["volatility_20d"] = (
        frame.groupby("symbol", sort=False)["ret_1d"]
        .rolling(20, min_periods=20)
        .std()
        .reset_index(level=0, drop=True)
    )
    frame = frame.sort_values(["trade_date", "symbol"])
    frame.to_parquet(path, index=False, compression="zstd")
    details["kline_adj.parquet"] = {
        **dict(details.get("kline_adj.parquet") or {}),
        "rows": len(frame),
        "signal_features": ["ret_5d", "ret_60d", "volatility_20d"],
        "purpose": "Chenxi Engine price and signal compatibility view",
    }


def build(base: Path, output: Path, data_version: str | None = None) -> dict:
    if output.exists():
        raise FileExistsError(f"output already exists: {output}")
    source_manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
    version = data_version or str(source_manifest["data_version"])
    staging = output.with_name(f".{output.name}.building")
    if staging.exists():
        shutil.rmtree(staging)
    shutil.copytree(base.resolve(), staging, symlinks=False)
    annual_paths = sorted(staging.glob("dividend_yield_20*.parquet"))
    if not annual_paths:
        raise FileNotFoundError("no annual dividend_yield files found")
    frames = []
    for path in annual_paths:
        frame = pd.read_parquet(path)
        if "dividend_yield" in frame.columns and "div_yield" not in frame.columns:
            frame = frame.rename(columns={"dividend_yield": "div_yield"})
        required = {"symbol", "date", "div_yield"}
        missing = required - set(frame.columns)
        if missing:
            raise ValueError(f"{path.name} missing columns: {sorted(missing)}")
        frames.append(frame[["symbol", "date", "div_yield"]])
    combined = (
        pd.concat(frames, ignore_index=True)
        .drop_duplicates(["symbol", "date"], keep="last")
        .sort_values(["date", "symbol"])
    )
    combined.to_parquet(staging / "dividend_yield.parquet", index=False, compression="zstd")
    details = dict(source_manifest.get("details") or {})
    _add_signal_features(staging, details)
    details["dividend_yield.parquet"] = {
        "rows": len(combined),
        "date_min": pd.to_datetime(combined["date"]).min().date().isoformat(),
        "date_max": pd.to_datetime(combined["date"]).max().date().isoformat(),
        "unit": "decimal",
        "purpose": "Chenxi Engine compatibility view",
    }
    manifest = finalize_manifest(staging, data_version=version, base_version=source_manifest.get("base_version") or version, details=details)
    staging.replace(output)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Add immutable Chenxi Engine compatibility views")
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--data-version")
    args = parser.parse_args()
    print(json.dumps(build(args.base, args.output, args.data_version), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
