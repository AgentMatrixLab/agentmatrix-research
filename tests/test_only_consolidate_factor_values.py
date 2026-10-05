"""TEST-ONLY tests for consolidating retained factor-value parts.

The consolidated file is the `--factor-file` the strategy demo and the cross-check read, so a
wrong concatenation would be consumed silently. The tests pin the three ways it could go
wrong: a variant leaking in, parts whose schemas disagree, and per-series row counts that are
not uniform (which would mean a part was captured mid-write).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from consolidate_factor_values import ConsolidateError, main, sha256_file  # noqa: E402

ROWS = 5


def _part(path: Path, names: list[str], *, rows: int = ROWS, schema_extra: bool = False) -> None:
    import numpy as np
    import pandas as pd

    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(["2020-01-02"] * rows * len(names)),
            "code": [f"{i:06d}" for i in range(rows)] * len(names),
            "factor_name": [n for n in names for _ in range(rows)],
            "value": np.array([float(i) for _ in names for i in range(rows)]),
        }
    )
    if schema_extra:
        frame["extra"] = 1
    pq.write_table(pa.Table.from_pandas(frame, preserve_index=False), path)


def _run(parts: Path, output: Path) -> int:
    return main(["--parts", str(parts), "--output", str(output)])


def test_only_concatenates_parts_and_writes_a_sidecar(tmp_path: Path) -> None:
    parts = tmp_path / "parts"
    parts.mkdir()
    _part(parts / "shard000.parquet", ["alpha_a", "alpha_b"])
    _part(parts / "shard001.parquet", ["alpha_c"])

    output = tmp_path / "factor_values.parquet"
    assert _run(parts, output) == 0

    table = pq.read_table(output)
    assert len(table) == ROWS * 3
    assert sorted(set(table.column("factor_name").to_pylist())) == ["alpha_a", "alpha_b", "alpha_c"]

    sidecar = json.loads(Path(f"{output}.json").read_text(encoding="utf-8"))
    assert sidecar["row_count"] == ROWS * 3
    assert "retained part" in sidecar["source"]
    assert sidecar["sha256"] == sha256_file(output)
    assert sidecar["factors"]["alpha_c"]["rows"] == ROWS
    # The demo reads `source` from this sidecar; it must not look synthetic.
    assert "SYNTHETIC" not in sidecar["source"].upper()


def test_only_refuses_a_perturbation_variant(tmp_path: Path) -> None:
    parts = tmp_path / "parts"
    parts.mkdir()
    _part(parts / "shard000.parquet", ["alpha_a", "alpha_a|window=8"])

    with pytest.raises(ConsolidateError, match="perturbation variant"):
        _run(parts, tmp_path / "out.parquet")


def test_only_refuses_parts_whose_schemas_disagree(tmp_path: Path) -> None:
    parts = tmp_path / "parts"
    parts.mkdir()
    _part(parts / "shard000.parquet", ["alpha_a"])
    _part(parts / "shard001.parquet", ["alpha_b"], schema_extra=True)

    with pytest.raises(ConsolidateError, match="different schema"):
        _run(parts, tmp_path / "out.parquet")


def test_only_accepts_a_single_part_file(tmp_path: Path) -> None:
    one = tmp_path / "only.parquet"
    _part(one, ["alpha_a"])
    output = tmp_path / "out.parquet"
    assert _run(one, output) == 0
    assert pq.read_table(output).num_rows == ROWS


def test_only_refuses_an_empty_directory(tmp_path: Path) -> None:
    empty = tmp_path / "parts"
    empty.mkdir()
    with pytest.raises(ConsolidateError, match="no parquet parts"):
        _run(empty, tmp_path / "out.parquet")
