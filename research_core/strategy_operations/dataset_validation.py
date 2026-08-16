from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.compute as pc
import pyarrow.parquet as pq

from research_core.strategy_operations.dataset_builder import sha256


CORE_FILES = {
    "kline_adj.parquet": {"symbol", "trade_date", "open", "close", "open_adj", "close_adj", "limit_up", "limit_down"},
    "security_status.parquet": {"symbol", "trade_date", "is_suspended", "is_st"},
    "stock_info.parquet": {"symbol", "is_listed"},
    "balance_sheet.parquet": {"symbol", "report_period", "ann_date", "total_equity"},
    "income_stmt.parquet": {"symbol", "report_period", "ann_date", "net_profit"},
    "csi300_index.parquet": {"date", "CSI300"},
    "calendar.parquet": {"trade_date"},
}


def parquet_max_date(path: Path, column: str) -> str | None:
    scalar = pc.max(pq.read_table(path, columns=[column])[column])
    if not scalar.is_valid:
        return None
    return pd.Timestamp(scalar.as_py()).date().isoformat()


def validate_dataset(root: str | Path, *, verify_hashes: bool = True) -> dict[str, Any]:
    root = Path(root)
    errors: list[str] = []
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        return {"status": "blocked", "data_version": None, "errors": ["manifest.json is missing"], "files": {}}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    data_version = str(manifest.get("data_version") or (manifest.get("details") or {}).get("kline_adj.parquet", {}).get("date_max") or "")
    files_report = {}
    for name, required_columns in CORE_FILES.items():
        path = root / name
        file_errors = []
        if not path.is_file():
            file_errors.append("file is missing")
        else:
            parquet = pq.ParquetFile(path)
            columns = set(parquet.schema.names)
            missing = sorted(required_columns - columns)
            if missing:
                file_errors.append(f"missing columns: {', '.join(missing)}")
            expected = (manifest.get("files") or {}).get(name)
            if not expected:
                file_errors.append("file is absent from manifest")
            else:
                if parquet.metadata.num_rows != expected.get("rows"):
                    file_errors.append("row count differs from manifest")
                if verify_hashes and sha256(path) != expected.get("sha256"):
                    file_errors.append("SHA-256 differs from manifest")
        files_report[name] = {"status": "failed" if file_errors else "ready", "errors": file_errors}
        errors.extend(f"{name}: {error}" for error in file_errors)
    dividend_paths = sorted(root.glob("dividend_yield_*.parquet"))
    if not dividend_paths:
        errors.append("dividend yield files are missing")
    else:
        latest_dividend = max(filter(None, (parquet_max_date(path, "date") for path in dividend_paths)), default=None)
        if latest_dividend != data_version:
            errors.append(f"dividend yield ends at {latest_dividend}, expected {data_version}")
    for name, column in (("kline_adj.parquet", "trade_date"), ("security_status.parquet", "trade_date"), ("csi300_index.parquet", "date"), ("calendar.parquet", "trade_date")):
        path = root / name
        if path.is_file():
            actual = parquet_max_date(path, column)
            if actual != data_version:
                errors.append(f"{name} ends at {actual}, expected {data_version}")
    return {"status": "ready" if data_version and not errors else "blocked", "data_version": data_version or None, "errors": errors, "files": files_report}
