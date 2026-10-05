"""Consolidate the retained factor-value parts into one dataset with a sidecar.

Why this exists
---------------
`retain_passing_values.py` saves the passing factors' base series one shard at a time, so the
values arrive as many small parts. Two consumers need a single file with a sibling
``<path>.json`` sidecar:

* `build_strategy_demos.py` refuses to run without one (`read_sidecar` looks for
  ``<factor-file>.json``), and it is the documented `--factor-file` for the delivery;
* `cross_check` verifies a declared digest against a named file, which a directory cannot
  provide.

Streaming the parts into one file is a row-group copy, so it is bounded in memory and cheap
relative to rebuilding the values (measured at ~4.4 hours at 450 factors).

    python -X utf8 scripts/consolidate_factor_values.py \
        --parts delivery/values/parts --output delivery/rebuild/factor_values.parquet
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pyarrow.parquet as pq

CN_TZ = timezone(timedelta(hours=8))
VALUE_COLUMNS = ("date", "code", "factor_name", "value")
VARIANT_MARKER = "|window="


class ConsolidateError(RuntimeError):
    """Raised when the parts cannot be consolidated honestly."""


def sha256_file(path: Path, chunk: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(chunk), b""):
            digest.update(block)
    return digest.hexdigest()


def resolve_parts(parts: Iterable[str | Path]) -> list[Path]:
    """Expand each argument (a directory, or a file) into parquet paths, deduplicated.

    Accepts several sources because the values can arrive two ways at once: the retention
    daemon covers most shards, and any shard it missed is rebuilt. Both have to end up in the
    single file the demo and the cross-check read.
    """
    if isinstance(parts, (str, Path)):
        parts = [parts]
    found: list[Path] = []
    for raw in parts:
        path = Path(raw)
        if path.is_dir():
            found.extend(sorted(path.glob("*.parquet")))
        elif path.is_file():
            found.append(path)
        else:
            raise ConsolidateError(f"factor value part not found: {path}")
    if not found:
        raise ConsolidateError("no parquet parts were found")
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in found:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(path)
    return unique


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--parts",
        required=True,
        nargs="+",
        help="one or more directories of parts, or parquet files",
    )
    parser.add_argument("--output", required=True)
    parser.add_argument("--batch-rows", type=int, default=1_048_576)
    args = parser.parse_args(argv)

    parts = resolve_parts(args.parts)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    writer: pq.ParquetWriter | None = None
    rows = 0
    series: dict[str, int] = {}
    origin: dict[str, str] = {}
    data_start: str | None = None
    data_end: str | None = None
    try:
        for part in parts:
            parquet = pq.ParquetFile(part)
            missing = sorted(set(VALUE_COLUMNS) - set(parquet.schema_arrow.names))
            if missing:
                raise ConsolidateError(f"{part.name} is missing columns: {', '.join(missing)}")
            if writer is None:
                writer = pq.ParquetWriter(output, schema=parquet.schema_arrow, compression="zstd")
            elif parquet.schema_arrow != writer.schema:
                raise ConsolidateError(
                    f"{part.name} has a different schema from the first part; concatenating "
                    "them would produce a file whose columns mean different things"
                )
            for batch in parquet.iter_batches(batch_size=args.batch_rows, columns=list(VALUE_COLUMNS)):
                names = batch.column("factor_name").to_pylist()
                for name in names:
                    if VARIANT_MARKER in name:
                        raise ConsolidateError(
                            f"a perturbation variant ({name!r}) is present in {part.name}; the "
                            "consolidated file is defined to carry base series only"
                        )
                    series[name] = series.get(name, 0) + 1
                # A factor must appear in exactly one source. Two sources holding the same factor
                # would duplicate every (date, code, factor_name) key, which the freeze rejects --
                # but only after the whole file has been written. Catch it while copying.
                for name in set(names):
                    previous = origin.setdefault(name, part.name)
                    if previous != part.name:
                        raise ConsolidateError(
                            f"factor {name!r} appears in both {previous} and {part.name}; "
                            "consolidating them would duplicate its keys. A rebuild covers every "
                            "passing factor, so it replaces the retained parts rather than "
                            "being merged with them."
                        )
                writer.write_batch(batch)
                rows += len(names)
                dates = batch.column("date")
                if len(dates):
                    low = str(dates[0].as_py())[:10]
                    high = str(dates[-1].as_py())[:10]
                    data_start = low if data_start is None or low < data_start else data_start
                    data_end = high if data_end is None or high > data_end else data_end
    finally:
        if writer is not None:
            writer.close()

    if rows == 0:
        raise ConsolidateError("no rows were copied; refusing to write an empty dataset")

    sidecar = {
        "source": f"scripts/consolidate_factor_values.py from {len(parts)} retained part(s)",
        "dataset": "factor_values",
        "data_start": data_start,
        "data_end": data_end,
        "row_count": int(rows),
        "sha256": sha256_file(output),
        "factors": {name: {"rows": count} for name, count in sorted(series.items())},
        "generated_at": datetime.now(CN_TZ).isoformat(timespec="seconds"),
        "parts": [part.name for part in parts],
    }
    sidecar_path = Path(f"{output}.json")
    sidecar_path.write_text(json.dumps(sidecar, ensure_ascii=False, indent=2), encoding="utf-8")

    counts = sorted(series.values())
    print(f"wrote {output}")
    print(f"  parts      : {len(parts)}")
    print(f"  rows       : {rows:,}")
    print(f"  base factor: {len(series)}")
    print(f"  rows/series: {counts[0]:,} .. {counts[-1]:,}"
          + ("  (all equal)" if counts[0] == counts[-1] else "  ** NOT UNIFORM **"))
    print(f"  range      : {data_start} .. {data_end}")
    print(f"  sidecar    : {sidecar_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
