"""Bounded-memory access to the factor-value long table.

Why this exists
---------------
`build_factor_values.py` writes a LONG table: one row per (date, code) per series, with
columns ``date, code, factor_name, value``. Two things about that table break the obvious
implementation at the real 2026-10-07 scale:

* **Size.** ~450 delivered factors carry a base series plus one series per perturbation
  multiplier, so the file reaches roughly ten billion rows. ``pd.read_parquet`` on it needs
  far more memory than the box has; the rehearsal at 12 factors was ~50x smaller and never
  exposed this.
* **Access pattern.** The natural way to pull one factor out,
  ``values[values["factor_name"] == factor_id]``, rescans the entire table once per factor.
  At 450 factors that is 450 full scans of ten billion rows.

Both are avoided by exploiting the layout the writer already guarantees: each series is a
contiguous run of rows, so a factor's values can be consumed in a single pass and released
immediately. Nothing here holds more than one series at a time (about 60 MB of values).

Row order is *verified*, not assumed
------------------------------------
Every series in a run is emitted from the same panel with the same emit filter, so the k-th
row of every series should be the same ``(date, code)``. Alignment code that merely assumes
this would silently mis-align values if it ever stopped being true, and a mis-aligned series
produces a plausible-looking IC rather than an error. `RowOrderReference` therefore compares
each series' keys against the first one and raises on any difference.

This module is additive: it is post-processing only and is not imported by, and cannot
influence, the frozen validator.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Sequence

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

__all__ = [
    "FactorSeries",
    "FactorValueStreamError",
    "RowOrderReference",
    "iter_factor_series",
    "is_perturbation_name",
    "resolve_factor_paths",
]

#: The four columns the factor-value dataset is defined to carry.
VALUE_COLUMNS = ("date", "code", "factor_name", "value")

#: `build_factor_values.py` names perturbation variants ``<factor_id>|window=<w>``.
VARIANT_MARKER = "|window="


class FactorValueStreamError(RuntimeError):
    """Raised when the factor-value table cannot be streamed honestly."""


def is_perturbation_name(factor_name: str) -> bool:
    """True for a perturbation variant rather than a base factor."""
    return VARIANT_MARKER in factor_name


def resolve_factor_paths(paths: Sequence[str | Path] | str | Path) -> list[Path]:
    """Expand a file, a directory, or a sequence of either into sorted Parquet paths.

    Accepting a directory matters at real scale: the values are retained one shard at a
    time, so they arrive as many part files rather than one.
    """
    if isinstance(paths, (str, Path)):
        paths = [paths]
    resolved: list[Path] = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            resolved.extend(sorted(path.glob("*.parquet")))
        elif path.is_file():
            resolved.append(path)
        else:
            raise FactorValueStreamError(f"factor value path does not exist: {path}")
    if not resolved:
        raise FactorValueStreamError("no factor value parquet files were found")
    return resolved


@dataclass
class FactorSeries:
    """One factor's values across the whole emitted range."""

    factor_id: str
    dates: pa.ChunkedArray
    codes: pa.ChunkedArray
    values: np.ndarray
    source: Path

    def __len__(self) -> int:
        return int(self.values.shape[0])


class RowOrderReference:
    """The `(date, code)` key sequence every series must share.

    Set once from the first series seen, then compared against every later series. The
    comparison runs in Arrow, so it costs milliseconds even at 7.7M rows and never
    materialises Python strings.
    """

    def __init__(self) -> None:
        self._dates: pa.ChunkedArray | None = None
        self._codes: pa.ChunkedArray | None = None
        self._length: int = 0
        self._factor_id: str | None = None
        self.comparisons: int = 0

    @property
    def length(self) -> int:
        return self._length

    @property
    def factor_id(self) -> str | None:
        """Which factor defined the reference order, for the report."""
        return self._factor_id

    def check(self, series: FactorSeries) -> None:
        if self._dates is None:
            self._dates = series.dates
            self._codes = series.codes
            self._length = len(series)
            self._factor_id = series.factor_id
            return

        if len(series) != self._length:
            raise FactorValueStreamError(
                f"factor {series.factor_id!r} in {series.source.name} carries {len(series)} rows "
                f"but {self._factor_id!r} carries {self._length}; the series are not aligned "
                "and must not be treated as a matrix"
            )
        self.comparisons += 1
        if not series.dates.equals(self._dates):
            raise FactorValueStreamError(
                f"factor {series.factor_id!r} in {series.source.name} has a different date "
                f"sequence from {self._factor_id!r}; assuming a shared row order would "
                "silently mis-align every value"
            )
        if not series.codes.equals(self._codes):
            raise FactorValueStreamError(
                f"factor {series.factor_id!r} in {series.source.name} has a different code "
                f"sequence from {self._factor_id!r}; assuming a shared row order would "
                "silently mis-align every value"
            )

    def keys(self) -> tuple[np.ndarray, np.ndarray]:
        """Reference keys as numpy arrays, for building an alignment index."""
        if self._dates is None or self._codes is None:
            raise FactorValueStreamError("the reference order was never set")
        dates = self._dates.to_numpy(zero_copy_only=False)
        codes = np.asarray(self._codes.to_pylist(), dtype=object)
        return dates, codes


def _codes_and_names(column: pa.Array) -> tuple[np.ndarray, list[str]]:
    """Integer codes plus the small dictionary they index, for boundary detection."""
    return dictionary_codes_and_names(column)


def dictionary_codes_and_names(column: pa.Array) -> tuple[np.ndarray, list[str]]:
    """Integer codes plus the small dictionary they index.

    Callers that need to know which series a batch holds should use this rather than
    ``to_pylist()``: on a 7.7M-row batch the latter builds 7.7M Python strings, which is the
    difference between milliseconds and seconds per series.
    """
    if pa.types.is_dictionary(column.type):
        return (
            column.indices.to_numpy(zero_copy_only=False).astype(np.int64, copy=False),
            column.dictionary.to_pylist(),
        )
    encoded = column.dictionary_encode()
    return (
        encoded.indices.to_numpy(zero_copy_only=False).astype(np.int64, copy=False),
        encoded.dictionary.to_pylist(),
    )


def iter_factor_series(
    paths: Sequence[str | Path],
    *,
    include_variants: bool = False,
    batch_rows: int = 1_048_576,
    reference: RowOrderReference | None = None,
    on_series=None,
) -> Iterator[FactorSeries]:
    """Yield one `FactorSeries` at a time, in file order, releasing each before the next.

    ``include_variants`` defaults to False because every consumer of this table -- the
    industry-neutral layer and the redundancy clustering -- is defined on base factors only.

    ``reference`` is checked for every series yielded, so a caller that passes one gets the
    row-order guarantee for free.
    """
    for path in resolve_factor_paths(paths):
        parquet = pq.ParquetFile(path)
        available = set(parquet.schema_arrow.names)
        missing = sorted(set(VALUE_COLUMNS) - available)
        if missing:
            raise FactorValueStreamError(f"{path} is missing columns: {', '.join(missing)}")

        date_parts: list[pa.Array] = []
        code_parts: list[pa.Array] = []
        value_parts: list[np.ndarray] = []
        current: str | None = None
        closed: set[str] = set()

        def flush(factor_id: str) -> FactorSeries:
            series = FactorSeries(
                factor_id=factor_id,
                dates=pa.chunked_array(date_parts),
                codes=pa.chunked_array(code_parts),
                values=np.concatenate(value_parts) if value_parts else np.empty(0, dtype=float),
                source=path,
            )
            date_parts.clear()
            code_parts.clear()
            value_parts.clear()
            return series

        for batch in parquet.iter_batches(
            batch_size=batch_rows,
            columns=list(VALUE_COLUMNS),
        ):
            names = batch.column("factor_name")
            dates = batch.column("date")
            codes = batch.column("code")
            values = batch.column("value").to_numpy(zero_copy_only=False)

            # A row group may straddle two series: the writer flushes on row count, not on
            # series boundaries, so boundaries are found per row -- but from the dictionary
            # CODES, not from materialised names.
            #
            # The first version called `to_pylist()` and then walked every row in Python,
            # comparing strings: 7.7M iterations per series, measured at ~7 s per series. That
            # is most of an hour for a 450-factor table, and the chain reads it more than once.
            # `np.diff` on the integer codes finds the same boundaries in milliseconds, and the
            # dictionary itself is a few hundred strings.
            code_values, names_by_code = _codes_and_names(names)
            boundaries = np.flatnonzero(code_values[1:] != code_values[:-1]) + 1
            segments = np.concatenate([[0], boundaries, [len(code_values)]])
            for start, stop in zip(segments[:-1], segments[1:]):
                name = names_by_code[code_values[start]]
                if name != current:
                    if current is not None:
                        if current in closed:
                            raise FactorValueStreamError(
                                f"factor {current!r} appears in more than one block of "
                                f"{path.name}; series are assumed contiguous"
                            )
                        closed.add(current)
                        if include_variants or not is_perturbation_name(current):
                            series = flush(current)
                            if reference is not None:
                                reference.check(series)
                            if on_series is not None:
                                on_series(series)
                            yield series
                        else:
                            date_parts.clear()
                            code_parts.clear()
                            value_parts.clear()
                    current = name
                date_parts.append(dates.slice(int(start), int(stop - start)))
                code_parts.append(codes.slice(int(start), int(stop - start)))
                value_parts.append(values[start:stop])

        if current is not None:
            if current in closed:
                raise FactorValueStreamError(
                    f"factor {current!r} appears in more than one block of {path.name}"
                )
            closed.add(current)
            if include_variants or not is_perturbation_name(current):
                series = flush(current)
                if reference is not None:
                    reference.check(series)
                if on_series is not None:
                    on_series(series)
                yield series
