from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
from pandas.api import types as ptypes


class PrecomputedFactorError(ValueError):
    """Raised when a precomputed factor-values Parquet file fails its contract."""


DATASET = "factor_values"
REQUIRED_COLUMNS = ("date", "code", "factor_name", "value")
_SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
_VARIANT_MARKER = "|window="


def perturbation_factor_name(factor_id: str, window: int) -> str:
    """Name used in the ``factor_name`` column for a perturbed parameterization."""
    return f"{factor_id}{_VARIANT_MARKER}{int(window)}"


def _as_path(value: str | Path, label: str) -> Path:
    path = Path(value)
    if not path.is_file():
        raise PrecomputedFactorError(f"{label} file does not exist: {path}")
    return path


def _sidecar_path(data_path: Path, sidecar_path: str | Path | None) -> Path:
    path = Path(sidecar_path) if sidecar_path is not None else Path(f"{data_path}.json")
    if not path.is_file():
        raise PrecomputedFactorError(f"sidecar file does not exist: {path}")
    return path


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise PrecomputedFactorError(f"cannot read Parquet file: {path}") from exc
    return digest.hexdigest()


def _read_sidecar(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PrecomputedFactorError(f"cannot read sidecar JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise PrecomputedFactorError("sidecar root must be a JSON object")

    required = {
        "source",
        "dataset",
        "data_start",
        "data_end",
        "row_count",
        "sha256",
        "factors",
        "value_definition",
    }
    missing = sorted(required - payload.keys())
    if missing:
        raise PrecomputedFactorError(f"sidecar is missing required fields: {', '.join(missing)}")
    if not isinstance(payload["source"], str) or not payload["source"].strip():
        raise PrecomputedFactorError("sidecar source must be a non-empty string")
    if payload["dataset"] != DATASET:
        raise PrecomputedFactorError(f"sidecar dataset must be {DATASET!r}")
    if not isinstance(payload["value_definition"], str) or not payload["value_definition"].strip():
        raise PrecomputedFactorError("sidecar value_definition must be a non-empty string")
    if isinstance(payload["row_count"], bool) or not isinstance(payload["row_count"], int):
        raise PrecomputedFactorError("sidecar row_count must be an integer")
    if payload["row_count"] < 1:
        raise PrecomputedFactorError("sidecar row_count must be positive")
    if not isinstance(payload["sha256"], str) or not _SHA256_PATTERN.fullmatch(payload["sha256"]):
        raise PrecomputedFactorError("sidecar sha256 must contain exactly 64 hexadecimal characters")

    for name in ("data_start", "data_end"):
        value = payload[name]
        if not isinstance(value, str):
            raise PrecomputedFactorError(f"sidecar {name} must use YYYY-MM-DD")
        try:
            parsed = date.fromisoformat(value)
        except ValueError as exc:
            raise PrecomputedFactorError(f"sidecar {name} must use YYYY-MM-DD") from exc
        if parsed.isoformat() != value:
            raise PrecomputedFactorError(f"sidecar {name} must use YYYY-MM-DD")
    if payload["data_start"] > payload["data_end"]:
        raise PrecomputedFactorError("sidecar data_start must not be after data_end")

    factors = payload["factors"]
    if not isinstance(factors, dict) or not factors:
        raise PrecomputedFactorError("sidecar factors must be a non-empty object")
    for factor_id, entry in factors.items():
        if not isinstance(factor_id, str) or not factor_id.strip():
            raise PrecomputedFactorError("sidecar factors keys must be non-empty strings")
        if _VARIANT_MARKER in factor_id:
            raise PrecomputedFactorError(
                f"sidecar factors key must be a base factor id without {_VARIANT_MARKER!r}: {factor_id!r}"
            )
        if not isinstance(entry, dict) or "window" not in entry:
            raise PrecomputedFactorError(f"sidecar factors[{factor_id!r}] must declare window")
        window = entry["window"]
        if isinstance(window, bool) or not isinstance(window, int) or window < 1:
            raise PrecomputedFactorError(f"sidecar factors[{factor_id!r}].window must be a positive integer")
    return payload


def _check_hash(path: Path, sidecar: dict[str, Any]) -> str:
    actual = _sha256_file(path)
    if not hmac.compare_digest(actual, sidecar["sha256"].lower()):
        raise PrecomputedFactorError("Parquet SHA-256 does not match sidecar")
    return actual


def _normalized_dates(values: pd.Series) -> pd.Series:
    if isinstance(values.dtype, pd.DatetimeTZDtype):
        raise PrecomputedFactorError("date must not contain timezone-aware timestamps")
    if ptypes.is_datetime64_any_dtype(values.dtype):
        parsed = values
    elif ptypes.is_object_dtype(values.dtype):
        allowed = (date, datetime, pd.Timestamp)
        non_null = values.dropna()
        if not non_null.map(lambda value: isinstance(value, allowed)).all():
            raise PrecomputedFactorError("date must contain Parquet date/timestamp values")
        parsed = pd.to_datetime(values, errors="coerce")
    else:
        raise PrecomputedFactorError("date must have a date or timestamp type")
    if parsed.isna().any():
        raise PrecomputedFactorError("date must not contain null values")
    invalid = values.notna() & parsed.isna()
    if invalid.any():
        raise PrecomputedFactorError("date contains invalid dates")
    if not parsed.eq(parsed.dt.normalize()).all():
        raise PrecomputedFactorError("date must contain dates without a time component")
    return parsed.dt.normalize()


def _string_column(frame: pd.DataFrame, column: str) -> pd.Series:
    values = frame[column]
    if values.isna().any() or not ptypes.is_string_dtype(values.dtype):
        raise PrecomputedFactorError(f"{column} must have a non-null string type")
    if not values.map(lambda value: isinstance(value, str) and bool(value.strip())).all():
        raise PrecomputedFactorError(f"{column} must contain non-empty strings")
    return values.astype(str)


def _validate_against_sidecar(frame: pd.DataFrame, sidecar: dict[str, Any]) -> None:
    actual_start = frame["date"].min().date().isoformat()
    actual_end = frame["date"].max().date().isoformat()
    if actual_start != sidecar["data_start"] or actual_end != sidecar["data_end"]:
        raise PrecomputedFactorError(
            "sidecar date range does not match Parquet rows "
            f"(expected {sidecar['data_start']}..{sidecar['data_end']}, "
            f"found {actual_start}..{actual_end})"
        )


def _declared_base(name: str, declared: Iterable[str]) -> str | None:
    if name in declared:
        return name
    if _VARIANT_MARKER not in name:
        return None
    base, _, suffix = name.partition(_VARIANT_MARKER)
    if not suffix.isdigit() or int(suffix) < 1:
        return None
    return base if base in declared else None


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
            raise PrecomputedFactorError(f"{label} must be a date or YYYY-MM-DD string") from exc
        if not isinstance(parsed, date):
            raise PrecomputedFactorError(f"{label} must be a date or YYYY-MM-DD string")
        if isinstance(parsed, datetime):
            parsed = parsed.date()
        if parsed != actual:
            raise PrecomputedFactorError(f"{label} mismatch (expected {parsed}, found {actual})")


@dataclass(frozen=True)
class PrecomputedFactorSet:
    """Validated long-table factor values, keyed by ``factor_name``."""

    path: Path
    sidecar: dict[str, Any]
    sha256: str
    series: dict[str, pd.Series]

    @property
    def factor_names(self) -> tuple[str, ...]:
        return tuple(sorted(self.series))

    def _require(self, name: str, *, purpose: str) -> pd.Series:
        values = self.series.get(name)
        if values is None:
            available = ", ".join(self.factor_names) or "<none>"
            raise PrecomputedFactorError(
                f"precomputed factor file cannot provide {purpose}: factor_name {name!r} is missing "
                f"(available: {available})"
            )
        return values

    def require(self, factor_id: str) -> pd.Series:
        return self._require(factor_id, purpose=f"factor {factor_id!r}")

    def base_window(self, factor_id: str) -> int:
        entry = self.sidecar["factors"].get(factor_id)
        if entry is None:
            raise PrecomputedFactorError(f"sidecar factors is missing base factor {factor_id!r}")
        return int(entry["window"])

    def require_perturbation(self, factor_id: str, window: int) -> pd.Series:
        name = perturbation_factor_name(factor_id, window)
        return self._require(
            name,
            purpose=f"the parameter_perturbation gate of {factor_id!r} at window {int(window)}",
        )

    def coverage_span(self) -> tuple[date, date]:
        return date.fromisoformat(self.sidecar["data_start"]), date.fromisoformat(self.sidecar["data_end"])


def load_precomputed_factors(
    path: str | Path,
    *,
    sidecar_path: str | Path | None = None,
    expected_start: str | date | None = None,
    expected_end: str | date | None = None,
) -> PrecomputedFactorSet:
    """Read and validate a local long-table factor-values Parquet; never accesses a network."""
    data_path = _as_path(path, "Parquet")
    metadata = _read_sidecar(_sidecar_path(data_path, sidecar_path))
    digest = _check_hash(data_path, metadata)

    try:
        frame = pd.read_parquet(data_path)
    except Exception as exc:
        raise PrecomputedFactorError(f"cannot read Parquet file: {data_path}") from exc
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        raise PrecomputedFactorError("Parquet file must contain at least one row")

    missing = sorted(set(REQUIRED_COLUMNS) - set(frame.columns))
    unexpected = sorted(set(frame.columns) - set(REQUIRED_COLUMNS))
    if missing or unexpected:
        details = []
        if missing:
            details.append(f"missing: {', '.join(missing)}")
        if unexpected:
            details.append(f"unexpected: {', '.join(unexpected)}")
        raise PrecomputedFactorError(
            "factor Parquet columns must be exactly "
            f"{', '.join(REQUIRED_COLUMNS)} ({'; '.join(details)})"
        )
    if len(frame) != metadata["row_count"]:
        raise PrecomputedFactorError(
            f"sidecar row_count mismatch (expected {metadata['row_count']}, found {len(frame)})"
        )

    frame = frame.copy()
    frame["date"] = _normalized_dates(frame["date"])
    frame["code"] = _string_column(frame, "code")
    frame["factor_name"] = _string_column(frame, "factor_name")

    values = frame["value"]
    if ptypes.is_bool_dtype(values.dtype) or not ptypes.is_numeric_dtype(values.dtype):
        raise PrecomputedFactorError("value must have a numeric type")
    numeric = values.to_numpy(dtype="float64", na_value=np.nan)
    non_null = ~np.isnan(numeric)
    if non_null.any() and not np.isfinite(numeric[non_null]).all():
        raise PrecomputedFactorError("value contains a non-finite value")
    frame["value"] = numeric

    if frame.duplicated(["date", "code", "factor_name"]).any():
        raise PrecomputedFactorError("factor Parquet contains duplicate (date, code, factor_name) keys")

    declared = set(metadata["factors"])
    present = set(frame["factor_name"].unique())
    undeclared = sorted(name for name in present if _declared_base(name, declared) is None)
    if undeclared:
        raise PrecomputedFactorError(
            "factor Parquet contains factor_name values that the sidecar does not declare: "
            + ", ".join(undeclared)
        )
    absent = sorted(declared - present)
    if absent:
        raise PrecomputedFactorError(
            "sidecar declares factors with no rows in the Parquet: " + ", ".join(absent)
        )

    _validate_against_sidecar(frame, metadata)
    _check_expected_range(frame, expected_start=expected_start, expected_end=expected_end)

    series = {
        str(name): pd.Series(
            group["value"].to_numpy(dtype="float64"),
            index=pd.MultiIndex.from_frame(group[["date", "code"]]),
        )
        for name, group in frame.groupby("factor_name", sort=True)
    }
    return PrecomputedFactorSet(
        path=data_path,
        sidecar=metadata,
        sha256=digest,
        series=series,
    )
