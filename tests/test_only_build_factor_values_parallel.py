"""TEST-ONLY tests for the parallel factor-value build.

The build is the one shard phase that can use spare cores: it is single-threaded, the box is
CPU-idle, and the shard's train/oos phases are memory-bound and cannot be spread. Measured
builds span 140 s to 1851 s depending on formula nesting, and for the expensive ones the build
is most of the shard.

But this script produces the values the frozen validator consumes, so "faster" is only
acceptable if it is also "identical". These tests require the parallel path to write a
byte-identical file, which is the strongest statement available: the sidecar's sha256 is a
hash of the file, so equal digests mean equal bytes.
"""

from __future__ import annotations

import csv
import hashlib
import json
import multiprocessing
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_factor_values as builder  # noqa: E402

FIELDS = [
    "factor_id", "name", "formula", "category", "required_fields",
    "direction", "risk_exposure", "window",
]


def _panel() -> pd.DataFrame:
    rng = np.random.default_rng(11)
    dates = pd.bdate_range("2022-01-03", periods=80)
    frames = []
    for index in range(3):
        close = (10.0 + index) * np.exp(np.cumsum(rng.normal(0.0005, 0.02, len(dates))))
        volume = rng.lognormal(13.5, 0.3, len(dates))
        frames.append(
            pd.DataFrame(
                {
                    "date": dates, "code": f"{index:06d}.XSHE",
                    "open": close * (1 + rng.normal(0, 0.003, len(dates))),
                    "high": close * 1.01, "low": close * 0.99, "close": close,
                    "volume": volume, "total_turnover": volume * close,
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


def _candidate(factor_id: str, formula: str, window: str) -> dict:
    return {
        "factor_id": factor_id, "name": factor_id, "formula": formula,
        "category": "技术因子", "required_fields": "CLOSE", "direction": "",
        "risk_exposure": "false", "window": window,
    }


def _prepare(tmp_path: Path, *, include_windowless: bool = False) -> tuple[Path, Path]:
    """A panel and a candidate list exercising the paths that matter.

    ``include_windowless`` adds a candidate the builder must REFUSE, which makes the whole run
    exit 1 by design -- kept out of the equivalence comparisons so those test one thing.
    """
    panel_path = tmp_path / "panel.parquet"
    _panel().to_parquet(panel_path, index=False)
    candidates = tmp_path / "candidates.csv"
    rows = [
        _candidate("REH:ma", "Mean($close, 20)", "20"),
        _candidate("REH:tiny", "Delta($close, 2)", "2"),
        _candidate("REH:corr", "Correlation($close, $volume, 10)", "10"),
    ]
    if include_windowless:
        rows.append(_candidate("REH:nowindow", "Mean($close, 5)", ""))
    with candidates.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return panel_path, candidates


def _build(tmp_path: Path, panel_path: Path, candidates: Path, name: str, jobs: int) -> int:
    output = tmp_path / f"{name}.parquet"
    return builder.main([
        "--candidates", str(candidates),
        "--panel-file", str(panel_path),
        "--config", str(ROOT / "configs" / "validation_gates.yaml"),
        "--output", str(output),
        "--report", str(tmp_path / f"{name}.report.json"),
        "--jobs", str(jobs),
    ])


def test_only_serial_build_is_unchanged_by_the_refactor(tmp_path: Path) -> None:
    """The series set, the refusal and the report must be as before the extraction."""
    panel_path, candidates = _prepare(tmp_path, include_windowless=True)
    # A refused candidate is a failure the builder reports by exiting non-zero, so a delivery
    # never quietly ships a factor the validator cannot see.
    assert _build(tmp_path, panel_path, candidates, "serial", jobs=1) == 1

    table = pd.read_parquet(tmp_path / "serial.parquet")
    names = list(dict.fromkeys(table["factor_name"].tolist()))
    assert "REH:ma" in names
    assert "REH:nowindow" not in names
    assert any("|window=" in name for name in names)

    report = json.loads((tmp_path / "serial.report.json").read_text(encoding="utf-8"))
    assert report["base_factors"] == 3
    assert any(f["factor_id"] == "REH:nowindow" for f in report["failures"])
    assert report["vacuous_perturbation"] == ["REH:tiny"]


@pytest.mark.skipif(
    "fork" not in multiprocessing.get_all_start_methods(),
    reason="the parallel build only engages where fork exists (the Linux deployment target)",
)
def test_only_parallel_build_writes_a_byte_identical_file(tmp_path: Path) -> None:
    """Equal sha256 means equal bytes: the strongest available equivalence statement.

    If this ever fails, the parallel path must not be enabled -- the file it writes is what the
    frozen validator judges, so a difference of any kind changes the delivery.
    """
    panel_path, candidates = _prepare(tmp_path)
    assert _build(tmp_path, panel_path, candidates, "serial", jobs=1) == 0
    assert _build(tmp_path, panel_path, candidates, "parallel", jobs=4) == 0

    serial = tmp_path / "serial.parquet"
    parallel = tmp_path / "parallel.parquet"
    serial_digest = hashlib.sha256(serial.read_bytes()).hexdigest()
    parallel_digest = hashlib.sha256(parallel.read_bytes()).hexdigest()
    assert serial_digest == parallel_digest, "the parallel build changed the written file"

    serial_sidecar = json.loads(Path(f"{serial}.json").read_text(encoding="utf-8"))
    parallel_sidecar = json.loads(Path(f"{parallel}.json").read_text(encoding="utf-8"))
    assert serial_sidecar["sha256"] == parallel_sidecar["sha256"]
    assert serial_sidecar["row_count"] == parallel_sidecar["row_count"]
    assert serial_sidecar["factors"] == parallel_sidecar["factors"]


@pytest.mark.skipif(
    "fork" not in multiprocessing.get_all_start_methods(),
    reason="the parallel build only engages where fork exists",
)
def test_only_parallel_build_reports_the_same_failures(tmp_path: Path) -> None:
    panel_path, candidates = _prepare(tmp_path, include_windowless=True)
    assert _build(tmp_path, panel_path, candidates, "serial", jobs=1) == 1
    assert _build(tmp_path, panel_path, candidates, "parallel", jobs=3) == 1

    serial = json.loads((tmp_path / "serial.report.json").read_text(encoding="utf-8"))
    parallel = json.loads((tmp_path / "parallel.report.json").read_text(encoding="utf-8"))
    for key in ("base_factors", "series", "rows", "vacuous_perturbation",
                "ambiguous_window_substitutions", "failures"):
        assert serial[key] == parallel[key], f"{key} differs between serial and parallel"
