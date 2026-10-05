"""TEST-ONLY tests for describing the batch a partial shard run actually covered.

The distinction matters for the cross-check: a run authorised for 849 candidates that stops
after N shards has evaluated only the candidates those shards held, so claiming 849 makes the
merged batch contradict its own results list. Writing the covered subset keeps the claim true
while the delivery manifest still lists every authorised candidate, with the unevaluated ones
as `not_run`.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_batch_candidates import BatchCandidateError, main  # noqa: E402

FIELDS = ["factor_id", "name", "formula", "window"]


def _full_list(path: Path, ids: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for factor_id in ids:
            writer.writerow(
                {"factor_id": factor_id, "name": factor_id, "formula": "close", "window": 10}
            )


def _shard(run: Path, tag: str, ids: list[str], *, done: bool = True) -> None:
    shard = run / "shards" / tag
    (shard / "oos").mkdir(parents=True, exist_ok=True)
    with (shard / "candidate_list.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for factor_id in ids:
            writer.writerow(
                {"factor_id": factor_id, "name": factor_id, "formula": "close", "window": 10}
            )
    if done:
        (shard / "oos" / "batch_manifest.json").write_text(
            json.dumps({"results": [{"factor_id": i, "status": "validated"} for i in ids]}),
            encoding="utf-8",
        )


def test_only_writes_the_union_of_completed_shards_in_full_list_order(tmp_path: Path) -> None:
    run = tmp_path / "run"
    _full_list(tmp_path / "all.csv", ["f1", "f2", "f3", "f4", "f5"])
    _shard(run, "shard000", ["f1", "f4"])
    _shard(run, "shard001", ["f2"])
    _shard(run, "shard002", ["f3"], done=False)  # not finished: must not count

    output = tmp_path / "batch.csv"
    assert main([
        "--run", str(run), "--candidates", str(tmp_path / "all.csv"), "--output", str(output),
    ]) == 0

    with output.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    # Full-list order, not shard order.
    assert [row["factor_id"] for row in rows] == ["f1", "f2", "f4"]


def test_only_refuses_when_nothing_has_completed(tmp_path: Path) -> None:
    run = tmp_path / "run"
    _full_list(tmp_path / "all.csv", ["f1", "f2"])
    _shard(run, "shard000", ["f1"], done=False)

    with pytest.raises(BatchCandidateError, match="no completed shard"):
        main([
            "--run", str(run), "--candidates", str(tmp_path / "all.csv"),
            "--output", str(tmp_path / "out.csv"),
        ])


def test_only_refuses_when_shards_disagree_with_the_authorised_list(tmp_path: Path) -> None:
    run = tmp_path / "run"
    _full_list(tmp_path / "all.csv", ["f1", "f2"])
    _shard(run, "shard000", ["something_else"])

    with pytest.raises(BatchCandidateError, match="disagree about what was authorised"):
        main([
            "--run", str(run), "--candidates", str(tmp_path / "all.csv"),
            "--output", str(tmp_path / "out.csv"),
        ])


def test_only_refuses_a_run_root_without_shards(tmp_path: Path) -> None:
    _full_list(tmp_path / "all.csv", ["f1"])
    with pytest.raises(BatchCandidateError, match="shards does not exist"):
        main([
            "--run", str(tmp_path / "nope"), "--candidates", str(tmp_path / "all.csv"),
            "--output", str(tmp_path / "out.csv"),
        ])
