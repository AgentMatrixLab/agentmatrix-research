from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from pandas.api import types as ptypes


class PanelSourceError(ValueError):
    """Raised when a local validation-panel Parquet fails its contract."""


DATASET = "validation_panel"
DATE_COLUMNS = ("date", "listed_date", "de_listed_date")
NUMERIC_COLUMNS = ("close", "volume", "total_turnover", "limit_up", "limit_down", "circulation_a")
BOOLEAN_COLUMNS = ("is_st", "is_suspended")
REQUIRED_COLUMNS = ("date", "code", *NUMERIC_COLUMNS, *BOOLEAN_COLUMNS, *DATE_COLUMNS[1:])
_SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")


def _as_path(value: str | Path, label: str) -> Path:
    path = Path(value)
    if not path.is_file():
        raise PanelSourceError(f"{label} file does not exist: {path}")
    return path


def _sidecar_path(data_path: Path, sidecar_path: str | Path | None) -> Path:
    path = Path(sidecar_path) if sidecar_path is not None else Path(f"{data_path}.json")
    if not path.is_file():
        raise PanelSourceError(f"sidecar file does not exist: {path}")
    return path


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise PanelSourceError(f"cannot read Parquet file: {path}") from exc
    return digest.hexdigest()


def _read_sidecar(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PanelSourceError(f"cannot read sidecar JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise PanelSourceError("sidecar root must be a JSON object")

    required = {"source", "dataset", "data_start", "data_end", "row_count", "sha256", "price_basis"}
    missing = sorted(required - payload.keys())
    if missing:
        raise PanelSourceError(f"sidecar is missing required fields: {', '.join(missing)}")
    if not isinstance(payload["source"], str) or not payload["source"].strip():
        raise PanelSourceError("sidecar source must be a non-empty string")
    if payload["dataset"] != DATASET:
        raise PanelSourceError(f"sidecar dataset must be {DATASET!r}")
    if not isinstance(payload["price_basis"], str) or not payload["price_basis"].strip():
        raise PanelSourceError("sidecar price_basis must be a non-empty string")
    if isinstance(payload["row_count"], bool) or not isinstance(payload["row_count"], int):
        raise PanelSourceError("sidecar row_count must be an integer")
    if payload["row_count"] < 1:
        raise PanelSourceError("sidecar row_count must be positive")
    if not isinstance(payload["sha256"], str) or not _SHA256_PATTERN.fullmatch(payload["sha256"]):
        raise PanelSourceError("sidecar sha256 must contain exactly 64 hexadecimal characters")
    for name in ("data_start", "data_end"):
        value = payload[name]
        if not isinstance(value, str):
            raise PanelSourceError(f"sidecar {name} must use YYYY-MM-DD")
        try:
            parsed = date.fromisoformat(value)
        except ValueError as exc:
            raise PanelSourceError(f"sidecar {name} must use YYYY-MM-DD") from exc
        if parsed.isoformat() != value:
            raise PanelSourceError(f"sidecar {name} must use YYYY-MM-DD")
    if payload["data_start"] > payload["data_end"]:
        raise PanelSourceError("sidecar data_start must not be after data_end")
    return payload


def _normalized_dates(series: pd.Series, column: str, *, nullable: bool) -> pd.Series:
    if isinstance(series.dtype, pd.DatetimeTZDtype):
        raise PanelSourceError(f"{column} must not contain timezone-aware timestamps")
    if ptypes.is_datetime64_any_dtype(series.dtype):
        parsed = series
    elif ptypes.is_object_dtype(series.dtype):
        allowed = (date, datetime, pd.Timestamp)
        non_null = series.dropna()
        if not non_null.map(lambda value: isinstance(value, allowed)).all():
            raise PanelSourceError(f"{column} must contain Parquet date/timestamp values")
        parsed = pd.to_datetime(series, errors="coerce")
    else:
        raise PanelSourceError(f"{column} must have a date or timestamp type")
    if not nullable and parsed.isna().any():
        raise PanelSourceError(f"{column} must not contain null values")
    if (series.notna() & parsed.isna()).any():
        raise PanelSourceError(f"{column} contains invalid dates")
    non_null = parsed.dropna()
    if not non_null.eq(non_null.dt.normalize()).all():
        raise PanelSourceError(f"{column} must contain dates without a time component")
    return parsed.dt.normalize()


def _validate_numeric(frame: pd.DataFrame, column: str) -> None:
    series = frame[column]
    if ptypes.is_bool_dtype(series.dtype) or not ptypes.is_numeric_dtype(series.dtype):
        raise PanelSourceError(f"{column} must have a numeric type")
    non_null = series.notna().to_numpy()
    numeric = series.to_numpy(dtype="float64", na_value=np.nan)
    if non_null.any() and not np.isfinite(numeric[non_null]).all():
        raise PanelSourceError(f"{column} contains a non-finite value")


@dataclass(frozen=True)
class LocalPanel:
    path: Path
    sidecar: dict[str, Any]
    sha256: str
    frame: pd.DataFrame

    @property
    def price_basis(self) -> str:
        return str(self.sidecar["price_basis"])


def load_validation_panel(
    path: str | Path,
    *,
    sidecar_path: str | Path | None = None,
    expected_start: str | date | None = None,
    expected_end: str | date | None = None,
) -> LocalPanel:
    """Read and validate a local validation-panel Parquet; never accesses a network.

    Columns must already use the validation pipeline's own names and price basis. This loader
    performs no renaming and no adjustment arithmetic: whatever price basis the sidecar
    declares is what the pipeline consumes, and it is recorded in the run manifest.
    """
    data_path = _as_path(path, "Parquet")
    metadata = _read_sidecar(_sidecar_path(data_path, sidecar_path))
    actual_digest = _sha256_file(data_path)
    if not hmac.compare_digest(actual_digest, metadata["sha256"].lower()):
        raise PanelSourceError("Parquet SHA-256 does not match sidecar")

    try:
        frame = pd.read_parquet(data_path)
    except Exception as exc:
        raise PanelSourceError(f"cannot read Parquet file: {data_path}") from exc
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        raise PanelSourceError("Parquet file must contain at least one row")
    if len(frame) != metadata["row_count"]:
        raise PanelSourceError(
            f"sidecar row_count mismatch (expected {metadata['row_count']}, found {len(frame)})"
        )

    missing = sorted(set(REQUIRED_COLUMNS) - set(frame.columns))
    if missing:
        raise PanelSourceError(f"panel is missing required columns: {', '.join(missing)}")

    frame = frame.copy()
    frame["date"] = _normalized_dates(frame["date"], "date", nullable=False)
    for column in DATE_COLUMNS[1:]:
        frame[column] = _normalized_dates(frame[column], column, nullable=column == "de_listed_date")
    if frame["listed_date"].isna().any():
        raise PanelSourceError("listed_date must not contain null values")

    codes = frame["code"]
    if codes.isna().any() or not ptypes.is_string_dtype(codes.dtype):
        raise PanelSourceError("code must have a non-null string type")
    if not codes.map(lambda value: isinstance(value, str) and bool(value.strip())).all():
        raise PanelSourceError("code must contain non-empty strings")
    frame["code"] = codes.astype(str)

    for column in NUMERIC_COLUMNS:
        _validate_numeric(frame, column)
    for column in BOOLEAN_COLUMNS:
        series = frame[column]
        if not ptypes.is_bool_dtype(series.dtype) or series.isna().any():
            raise PanelSourceError(f"{column} must have a non-null boolean type")

    if frame.duplicated(["date", "code"]).any():
        raise PanelSourceError("panel contains duplicate (date, code) keys")

    actual_start = frame["date"].min().date().isoformat()
    actual_end = frame["date"].max().date().isoformat()
    if actual_start != metadata["data_start"] or actual_end != metadata["data_end"]:
        raise PanelSourceError(
            "sidecar date range does not match Parquet rows "
            f"(expected {metadata['data_start']}..{metadata['data_end']}, "
            f"found {actual_start}..{actual_end})"
        )
    for label, expected, actual in (
        ("expected_start", expected_start, frame["date"].min().date()),
        ("expected_end", expected_end, frame["date"].max().date()),
    ):
        if expected is None:
            continue
        try:
            parsed = date.fromisoformat(expected) if isinstance(expected, str) else expected
        except ValueError as exc:
            raise PanelSourceError(f"{label} must be a date or YYYY-MM-DD string") from exc
        if isinstance(parsed, datetime):
            parsed = parsed.date()
        if not isinstance(parsed, date) or parsed != actual:
            raise PanelSourceError(f"{label} mismatch (expected {parsed}, found {actual})")

    return LocalPanel(path=data_path, sidecar=metadata, sha256=actual_digest, frame=frame)
