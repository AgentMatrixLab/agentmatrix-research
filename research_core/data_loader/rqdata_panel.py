from __future__ import annotations

import hashlib
import hmac
import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from pandas.api import types as ptypes


class RQDataPanelError(ValueError):
    """Raised when a local RQData Parquet file fails its data contract."""


_PANEL_COLUMNS = {
    "date",
    "code",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
    "adjustment_factor",
    "is_suspended",
    "is_st",
    "listing_date",
    "delisting_date",
    "limit_up",
    "limit_down",
}
_PANEL_NUMERIC_COLUMNS = {
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
    "adjustment_factor",
    "limit_up",
    "limit_down",
}
_BENCHMARK_COLUMNS = {"date", "return"}
_SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")


def _as_path(value: str | Path, label: str) -> Path:
    path = Path(value)
    if not path.is_file():
        raise RQDataPanelError(f"{label} file does not exist: {path}")
    return path


def _sidecar_path(data_path: Path, sidecar_path: str | Path | None) -> Path:
    path = Path(sidecar_path) if sidecar_path is not None else Path(f"{data_path}.json")
    if not path.is_file():
        raise RQDataPanelError(f"sidecar file does not exist: {path}")
    return path


def _read_sidecar(path: Path, *, dataset: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RQDataPanelError(f"cannot read sidecar JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise RQDataPanelError("sidecar root must be a JSON object")

    required = {"source", "dataset", "data_start", "data_end", "row_count", "sha256"}
    missing = sorted(required - payload.keys())
    if missing:
        raise RQDataPanelError(f"sidecar is missing required fields: {', '.join(missing)}")
    if not isinstance(payload["source"], str) or not payload["source"].strip():
        raise RQDataPanelError("sidecar source must be a non-empty string")
    if payload["dataset"] != dataset:
        raise RQDataPanelError(f"sidecar dataset must be {dataset!r}")
    if isinstance(payload["row_count"], bool) or not isinstance(payload["row_count"], int):
        raise RQDataPanelError("sidecar row_count must be an integer")
    if payload["row_count"] < 1:
        raise RQDataPanelError("sidecar row_count must be positive")
    if not isinstance(payload["sha256"], str) or not _SHA256_PATTERN.fullmatch(payload["sha256"]):
        raise RQDataPanelError("sidecar sha256 must contain exactly 64 hexadecimal characters")

    for name in ("data_start", "data_end"):
        value = payload[name]
        if not isinstance(value, str):
            raise RQDataPanelError(f"sidecar {name} must use YYYY-MM-DD")
        try:
            parsed = date.fromisoformat(value)
        except ValueError as exc:
            raise RQDataPanelError(f"sidecar {name} must use YYYY-MM-DD") from exc
        if parsed.isoformat() != value:
            raise RQDataPanelError(f"sidecar {name} must use YYYY-MM-DD")
    if payload["data_start"] > payload["data_end"]:
        raise RQDataPanelError("sidecar data_start must not be after data_end")
    return payload


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise RQDataPanelError(f"cannot read Parquet file: {path}") from exc
    return digest.hexdigest()


def _check_hash(path: Path, sidecar: dict[str, Any]) -> None:
    actual = _sha256_file(path)
    if not hmac.compare_digest(actual, sidecar["sha256"].lower()):
        raise RQDataPanelError("Parquet SHA-256 does not match sidecar")


def _date_series(frame: pd.DataFrame, column: str, *, nullable: bool) -> pd.Series:
    values = frame[column]
    if ptypes.is_datetime64_any_dtype(values.dtype):
        if ptypes.is_datetime64tz_dtype(values.dtype):
            raise RQDataPanelError(f"{column} must not contain timezone-aware timestamps")
        parsed = values
    elif ptypes.is_object_dtype(values.dtype):
        non_null = values.dropna()
        allowed = (date, datetime, pd.Timestamp)
        if not non_null.map(lambda value: isinstance(value, allowed)).all():
            raise RQDataPanelError(f"{column} must contain Parquet date/timestamp values")
        parsed = pd.to_datetime(values, errors="coerce")
    else:
        raise RQDataPanelError(f"{column} must have a date or timestamp type")

    if ptypes.is_datetime64tz_dtype(parsed.dtype):
        raise RQDataPanelError(f"{column} must not contain timezone-aware timestamps")
    if not nullable and parsed.isna().any():
        raise RQDataPanelError(f"{column} must not contain null values")
    invalid = values.notna() & parsed.isna()
    if invalid.any():
        raise RQDataPanelError(f"{column} contains invalid dates")
    non_null = parsed.dropna()
    if not non_null.eq(non_null.dt.normalize()).all():
        raise RQDataPanelError(f"{column} must contain dates without a time component")
    return parsed.dt.normalize()


def _validate_dates(frame: pd.DataFrame, sidecar: dict[str, Any]) -> None:
    actual_start = frame["date"].min().date().isoformat()
    actual_end = frame["date"].max().date().isoformat()
    if actual_start != sidecar["data_start"] or actual_end != sidecar["data_end"]:
        raise RQDataPanelError(
            "sidecar date range does not match Parquet rows "
            f"(expected {sidecar['data_start']}..{sidecar['data_end']}, "
            f"found {actual_start}..{actual_end})"
        )


def _validate_numeric_column(frame: pd.DataFrame, column: str) -> None:
    values = frame[column]
    if not ptypes.is_numeric_dtype(values.dtype) or ptypes.is_bool_dtype(values.dtype):
        raise RQDataPanelError(f"{column} must have a numeric type")
    non_null = values.notna().to_numpy()
    numeric_values = values.to_numpy(dtype="float64", na_value=np.nan)
    if non_null.any() and not np.isfinite(numeric_values[non_null]).all():
        raise RQDataPanelError(f"{column} contains a non-finite value")


def _read_frame(path: Path, sidecar: dict[str, Any]) -> pd.DataFrame:
    _check_hash(path, sidecar)
    try:
        frame = pd.read_parquet(path)
    except Exception as exc:
        raise RQDataPanelError(f"cannot read Parquet file: {path}") from exc
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        raise RQDataPanelError("Parquet file must contain at least one row")
    if len(frame) != sidecar["row_count"]:
        raise RQDataPanelError(
            f"sidecar row_count mismatch (expected {sidecar['row_count']}, found {len(frame)})"
        )
    return frame


def load_rqdata_panel(
    panel_path: str | Path,
    *,
    sidecar_path: str | Path | None = None,
    expected_start: str | date | None = None,
    expected_end: str | date | None = None,
) -> pd.DataFrame:
    """Read and validate a local RQData all-A daily panel; never accesses a network."""
    path = _as_path(panel_path, "Parquet")
    metadata = _read_sidecar(_sidecar_path(path, sidecar_path), dataset="daily_panel")
    if metadata.get("price_basis") != "unadjusted_ohlc_with_adjustment_factor":
        raise RQDataPanelError("sidecar price_basis is missing or unsupported")
    if not isinstance(metadata.get("adjustment_factor_definition"), str) or not metadata[
        "adjustment_factor_definition"
    ].strip():
        raise RQDataPanelError("sidecar adjustment_factor_definition must be non-empty")

    frame = _read_frame(path, metadata)
    missing = sorted(_PANEL_COLUMNS - set(frame.columns))
    if missing:
        raise RQDataPanelError(f"panel is missing required columns: {', '.join(missing)}")
    if frame["code"].isna().any() or not ptypes.is_string_dtype(frame["code"].dtype):
        raise RQDataPanelError("code must have a non-null string type")
    if not frame["code"].map(lambda value: isinstance(value, str) and bool(value.strip())).all():
        raise RQDataPanelError("code must contain non-empty strings")

    for column in ("date", "listing_date", "delisting_date"):
        frame[column] = _date_series(frame, column, nullable=column != "date")
    for column in _PANEL_NUMERIC_COLUMNS:
        _validate_numeric_column(frame, column)
    if frame["adjustment_factor"].isna().any() or (frame["adjustment_factor"].dropna() <= 0).any():
        raise RQDataPanelError("adjustment_factor must contain finite positive values")
    for column in ("is_suspended", "is_st"):
        if not ptypes.is_bool_dtype(frame[column].dtype) or frame[column].isna().any():
            raise RQDataPanelError(f"{column} must have a non-null boolean type")

    if frame.duplicated(["date", "code"]).any():
        raise RQDataPanelError("panel contains duplicate (date, code) keys")
    _validate_dates(frame, metadata)
    _check_expected_range(frame, expected_start=expected_start, expected_end=expected_end)
    return frame


def load_rqdata_benchmark(
    benchmark_path: str | Path,
    *,
    sidecar_path: str | Path | None = None,
    expected_start: str | date | None = None,
    expected_end: str | date | None = None,
) -> pd.DataFrame:
    """Read and validate a local 000985 daily-return file; never accesses a network."""
    path = _as_path(benchmark_path, "Parquet")
    metadata = _read_sidecar(
        _sidecar_path(path, sidecar_path), dataset="benchmark_daily_return"
    )
    if metadata.get("benchmark_code") != "000985":
        raise RQDataPanelError("benchmark sidecar benchmark_code must be '000985'")
    if metadata.get("return_type") not in {"price_return", "total_return"}:
        raise RQDataPanelError("benchmark sidecar return_type must be price_return or total_return")

    frame = _read_frame(path, metadata)
    missing = sorted(_BENCHMARK_COLUMNS - set(frame.columns))
    if missing:
        raise RQDataPanelError(f"benchmark is missing required columns: {', '.join(missing)}")
    frame["date"] = _date_series(frame, "date", nullable=False)
    _validate_numeric_column(frame, "return")
    if frame["return"].isna().any():
        raise RQDataPanelError("benchmark return must not contain null values")
    if frame["date"].duplicated().any():
        raise RQDataPanelError("benchmark contains duplicate date keys")
    _validate_dates(frame, metadata)
    _check_expected_range(frame, expected_start=expected_start, expected_end=expected_end)
    return frame


def _check_expected_range(
    frame: pd.DataFrame,
    *,
    expected_start: str | date | None,
    expected_end: str | date | None,
) -> None:
    for label, expected, actual in (
        ("expected_start", expected_start, frame["date"].min().date()),
        ("expected_end", expected_end, frame["date"].max().date()),
    ):
        if expected is None:
            continue
        try:
            parsed = date.fromisoformat(expected) if isinstance(expected, str) else expected
        except ValueError as exc:
            raise RQDataPanelError(f"{label} must be a date or YYYY-MM-DD string") from exc
        if not isinstance(parsed, date):
            raise RQDataPanelError(f"{label} must be a date or YYYY-MM-DD string")
        if isinstance(parsed, datetime):
            parsed = parsed.date()
        if parsed != actual:
            raise RQDataPanelError(f"{label} mismatch (expected {parsed}, found {actual})")
