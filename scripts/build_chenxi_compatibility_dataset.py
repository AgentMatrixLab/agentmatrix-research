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
