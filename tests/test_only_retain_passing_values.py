"""TEST-ONLY tests for the passing-factor value retention daemon.

The daemon has to be right about one thing above all: it must never write a part that does
not faithfully hold the passing factors' base series. A wrong part is worse than a missing
one, because a missing part is caught later by the rebuild fallback while a wrong part is
consumed silently by the supplementary layer.

It also runs unattended against a live worker pool, so the tests pin the two behaviours that
make that safe: it will not capture a factor file that is still being written, and it drops
the hard link once the part is written so disk is not held.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "dev"))

from retain_passing_values import VARIANT_MARKER, retain_one  # noqa: E402

ROWS_PER_SERIES = 40

#: Verdicts held back by `with_verdict=False`, keyed by shard directory.
_PENDING_VERDICT: dict[Path, list] = {}


def _write_shard(
    root: Path,
    tag: str,
    *,
    passing: tuple[str, ...],
    rejected: tuple[str, ...] = (),
    rows_per_series: int = ROWS_PER_SERIES,
    report_older_than_values: bool = False,
    with_verdict: bool = True,
) -> Path:
    shard = root / "shards" / tag
    (shard / "oos").mkdir(parents=True, exist_ok=True)

    names: list[str] = []
    for factor_id in (*passing, *rejected):
        names.append(factor_id)
        names.append(f"{factor_id}{VARIANT_MARKER}8")

    table = pa.table(
        {
            "date": pa.array(
                [f"2020-01-{i % 28 + 1:02d}" for i in range(rows_per_series)] * len(names),
                type=pa.string(),
            ),
            "code": pa.array([f"{i:06d}" for i in range(rows_per_series)] * len(names)),
            "factor_name": pa.array([n for n in names for _ in range(rows_per_series)]),
            "value": pa.array([float(i) for _ in names for i in range(rows_per_series)]),
        }
    )
    pq.write_table(table, shard / "factor_values.parquet")

    (shard / "build_report.json").write_text(
        json.dumps({"series": len(names), "rows": rows_per_series * len(names)}),
        encoding="utf-8",
    )

    results = [
        {"factor_id": fid, "status": "validated", "failed_gates": []} for fid in passing
    ] + [
        {"factor_id": fid, "status": "rejected", "failed_gates": ["residual_ic"]}
        for fid in rejected
    ]
    if with_verdict:
        (shard / "oos" / "batch_manifest.json").write_text(
            json.dumps({"results": results}), encoding="utf-8"
        )
    else:
        # Held back so the test can exercise the window between "values exist" and
        # "verdict known", which is when the hard link is the only thing holding the data.
        _PENDING_VERDICT[shard] = results

    if report_older_than_values:
        import os

        values = (shard / "factor_values.parquet").stat()
        os.utime(shard / "build_report.json", (values.st_mtime - 600, values.st_mtime - 600))
    return shard


def _write_verdict(shard: Path) -> None:
    (shard / "oos" / "batch_manifest.json").write_text(
        json.dumps({"results": _PENDING_VERDICT[shard]}), encoding="utf-8"
    )


def _run(shard: Path, tmp_path: Path, settled: dict | None = None) -> dict:
    return retain_one(
        shard,
        retain_root=tmp_path / "values",
        rows_per_series=None,
        settled={} if settled is None else settled,
        log=lambda _message: None,
    )


def test_only_keeps_only_the_passing_base_series(tmp_path: Path) -> None:
    shard = _write_shard(tmp_path, "shard000", passing=("ALPHA:A",), rejected=("ALPHA:B",))
    settled: dict = {}
    assert _run(shard, tmp_path, settled)["action"] == "settling"

    state = _run(shard, tmp_path, settled)
    assert state["action"] == "retained"
    assert state["factors"] == 1

    part = tmp_path / "values" / "parts" / "shard000.parquet"
    table = pq.read_table(part)
    kept = sorted(set(table.column("factor_name").to_pylist()))
    assert kept == ["ALPHA:A"], "the part must hold the base series of passers only"
    assert len(table) == ROWS_PER_SERIES
    # The variant of the passing factor and the rejected factor must both be gone.
    assert not any(VARIANT_MARKER in name for name in kept)


def test_only_releases_the_hard_link_once_the_part_exists(tmp_path: Path) -> None:
    """Between "values exist" and "verdict known" the link is the only thing holding them."""
    shard = _write_shard(tmp_path, "shard000", passing=("ALPHA:A",), with_verdict=False)
    settled: dict = {}
    _run(shard, tmp_path, settled)
    _run(shard, tmp_path, settled)
    link = tmp_path / "values" / "raw" / "shard000.parquet"
    assert link.exists(), "the values must be held while the verdict is still unknown"
    assert not (tmp_path / "values" / "parts" / "shard000.parquet").exists()

    _write_verdict(shard)
    assert _run(shard, tmp_path, settled)["action"] == "retained"
    assert not link.exists(), "holding the link after the part exists would waste disk"


def test_only_refuses_to_capture_a_factor_file_that_is_still_being_written(tmp_path: Path) -> None:
    """A build report older than the values is a leftover from a previous attempt."""
    shard = _write_shard(
        tmp_path, "shard000", passing=("ALPHA:A",), report_older_than_values=True
    )
    settled: dict = {}
    for _ in range(3):
        assert _run(shard, tmp_path, settled)["action"] == "none"
    assert not (tmp_path / "values" / "raw" / "shard000.parquet").exists()
    assert not (tmp_path / "values" / "parts" / "shard000.parquet").exists()


def test_only_records_no_passers_without_writing_a_part(tmp_path: Path) -> None:
    shard = _write_shard(tmp_path, "shard000", passing=(), rejected=("ALPHA:B",))
    settled: dict = {}
    _run(shard, tmp_path, settled)
    _run(shard, tmp_path, settled)
    assert _run(shard, tmp_path, settled)["action"] == "no_passers"
    assert not (tmp_path / "values" / "parts" / "shard000.parquet").exists()
    assert not (tmp_path / "values" / "raw" / "shard000.parquet").exists()


def test_only_is_idempotent(tmp_path: Path) -> None:
    shard = _write_shard(tmp_path, "shard000", passing=("ALPHA:A",))
    settled: dict = {}
    _run(shard, tmp_path, settled)
    _run(shard, tmp_path, settled)
    part = tmp_path / "values" / "parts" / "shard000.parquet"
    first = part.read_bytes()
    assert _run(shard, tmp_path, settled)["action"] == "already_retained"
    assert part.read_bytes() == first


def test_only_drops_a_stale_link_left_after_the_part_is_written(tmp_path: Path) -> None:
    """A leftover link would hold ~800 MB per shard for the rest of the run."""
    shard = _write_shard(tmp_path, "shard000", passing=("ALPHA:A",))
    settled: dict = {}
    _run(shard, tmp_path, settled)
    _run(shard, tmp_path, settled)

    link = tmp_path / "values" / "raw" / "shard000.parquet"
    # Simulate what a re-run leaves behind: a link that survived the part being written.
    import os

    os.link(shard / "factor_values.parquet", link)
    assert link.exists()

    assert _run(shard, tmp_path, settled)["action"] == "already_retained"
    assert not link.exists(), "the stale link must be cleaned up"
    assert (tmp_path / "values" / "parts" / "shard000.parquet").is_file()


def test_only_rejects_a_part_whose_row_counts_do_not_match_the_report(tmp_path: Path) -> None:
    """If the factor file disagrees with its own build report, keep nothing."""
    shard = _write_shard(tmp_path, "shard000", passing=("ALPHA:A",))
    (shard / "build_report.json").write_text(
        json.dumps({"series": 2, "rows": (ROWS_PER_SERIES + 7) * 2}), encoding="utf-8"
    )
    import os

    values = (shard / "factor_values.parquet").stat()
    os.utime(shard / "build_report.json", (values.st_mtime, values.st_mtime + 1))

    settled: dict = {}
    _run(shard, tmp_path, settled)
    _run(shard, tmp_path, settled)
    state = _run(shard, tmp_path, settled)
    assert state["action"] != "retained"
    assert not (tmp_path / "values" / "parts" / "shard000.parquet").exists()


@pytest.mark.parametrize("tag", ["shard001", "shard042"])
def test_only_uses_the_shard_tag_as_the_part_name(tmp_path: Path, tag: str) -> None:
    shard = _write_shard(tmp_path, tag, passing=("ALPHA:A",))
    settled: dict = {}
    _run(shard, tmp_path, settled)
    _run(shard, tmp_path, settled)
    assert (tmp_path / "values" / "parts" / f"{tag}.parquet").is_file()
