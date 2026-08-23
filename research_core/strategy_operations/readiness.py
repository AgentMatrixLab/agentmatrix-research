from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd


def _pyarrow_modules():
    try:
        import pyarrow.compute as pc
        import pyarrow.parquet as pq
    except ModuleNotFoundError as exc:
        raise RuntimeError("pyarrow is required to inspect parquet readiness datasets") from exc
    return pc, pq


def _max_date(paths: list[Path], column: str) -> str | None:
    pc, pq = _pyarrow_modules()
    maximum: pd.Timestamp | None = None
    for path in paths:
        table = pq.read_table(path, columns=[column])
        scalar = pc.max(table[column])
        current = pd.to_datetime(scalar.as_py(), errors="coerce") if scalar.is_valid else pd.NaT
        if pd.notna(current) and (maximum is None or current > maximum):
            maximum = current
    return maximum.date().isoformat() if maximum is not None else None


def inspect_dataset(root: Path, spec: dict[str, Any]) -> dict[str, Any]:
    _, pq = _pyarrow_modules()
    paths = sorted(root.glob(spec["glob"]))
    errors: list[str] = []
    rows = 0
    columns: set[str] = set()
    if not paths:
        errors.append(f"no files match {spec['glob']}")
    for path in paths:
        parquet = pq.ParquetFile(path)
        rows += parquet.metadata.num_rows
        file_columns = set(parquet.schema.names)
        columns.update(file_columns)
        missing = sorted(set(spec.get("required_columns", [])) - file_columns)
        if missing:
            errors.append(f"{path.name} missing columns: {', '.join(missing)}")
    if paths and rows <= 0:
        errors.append("dataset has no rows")
    max_date = None
    date_column = spec.get("date_column")
    if paths and date_column and date_column in columns:
        try:
            max_date = _max_date(paths, date_column)
        except Exception as exc:
            errors.append(f"cannot read date column {date_column}: {exc}")
    return {
        "id": spec["id"],
        "required": bool(spec.get("required", True)),
        "status": "failed" if errors else "inspected",
        "files": [str(path.relative_to(root)) for path in paths],
        "rows": rows,
        "columns": sorted(columns),
        "max_date": max_date,
        "errors": errors,
    }


def build_readiness_manifest(root: str | Path, config: dict[str, Any]) -> dict[str, Any]:
    root = Path(root)
    inspections = {spec["id"]: inspect_dataset(root, spec) for spec in config.get("datasets", [])}
    source_id = config.get("data_version_source")
    data_version = (inspections.get(source_id) or {}).get("max_date")
    global_errors: list[str] = []
    if not data_version:
        global_errors.append(f"data version source {source_id!r} has no maximum date")
    for spec in config.get("datasets", []):
        item = inspections[spec["id"]]
        if not item["errors"] and data_version:
            freshness = spec.get("freshness", "present")
            if freshness == "data_version" and item["max_date"] != data_version:
                item["errors"].append(f"maximum date {item['max_date']} does not match data version {data_version}")
            elif freshness == "max_age_days":
                if not item["max_date"]:
                    item["errors"].append("maximum date is unavailable")
                else:
                    age = (date.fromisoformat(data_version) - date.fromisoformat(item["max_date"])).days
                    if not math.isfinite(age) or age < 0 or age > int(spec["max_age_days"]):
                        item["errors"].append(f"maximum date {item['max_date']} is {age} days behind data version {data_version}")
        item["status"] = "failed" if item["errors"] else "ready"
    required_failures = [item["id"] for item in inspections.values() if item["required"] and item["status"] != "ready"]
    return {
        "schema_version": "agentmatrix_data_readiness_v1",
        "status": "ready" if data_version and not global_errors and not required_failures else "blocked",
        "data_version": data_version,
        "root": str(root.resolve()),
        "required_failures": required_failures,
        "errors": global_errors,
        "datasets": list(inspections.values()),
    }


def load_readiness_config(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("Unsupported data readiness schema_version")
    return payload
