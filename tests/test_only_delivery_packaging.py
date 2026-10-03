"""TEST-ONLY tests for the factor catalog and the delivery packaging rule.

All result files here are hand-written fixtures that mimic what the pipeline writes. This
proves the packaging rule (only ``validated`` factors ship) and the failure reporting.
"""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from research_core.factor_lab.factor_catalog import (
    CATALOG_COLUMNS,
    build_factor_catalog,
    index_from_results_root,
    write_factor_catalog,
)
from research_core.factor_lab.package_delivery import (
    DeliveryPackagingError,
    build_delivery_package,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

GOOD = "reversal_1m"
BAD = "momentum_20"
STUCK = "rsi_6"
NEVER_RUN = "alpha002"


def _write_result(root: Path, factor_id: str, payload: dict, *, with_manifest: bool = True) -> None:
    factor_dir = root / factor_id
    factor_dir.mkdir(parents=True, exist_ok=True)
    (factor_dir / "validation_result.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (factor_dir / "validation_report.md").write_text(
        f"status={payload['status']}\n", encoding="utf-8"
    )
    if with_manifest:
        (factor_dir / "run_manifest.json").write_text(
            json.dumps(
                {
                    "result_hash": hashlib.sha256(factor_id.encode()).hexdigest(),
                    "params_hash": hashlib.sha256(b"params" + factor_id.encode()).hexdigest(),
                    "code_commit": "0" * 40,
                },
                indent=2,
            ),
            encoding="utf-8",
        )


def _results_root(tmp_path: Path) -> Path:
    root = tmp_path / "runs"
    _write_result(
        root,
        GOOD,
        {
            "status": "validated",
            "failed_gates": [],
            "gates": [{"name": "rank_ic", "passed": True, "actual": {"mean": 0.02}, "threshold": {}}],
        },
    )
    _write_result(
        root,
        BAD,
        {
            "status": "rejected",
            "failed_gates": ["rank_ic"],
            "gates": [
                {
                    "name": "rank_ic",
                    "passed": False,
                    "actual": {"mean": 0.001},
                    "threshold": {"minimum_abs_mean": 0.01},
                }
            ],
        },
    )
    stuck_dir = root / STUCK
    stuck_dir.mkdir(parents=True, exist_ok=True)
    (stuck_dir / "needs_human.json").write_text(
        json.dumps({"status": "needs_human", "reason": "Missing fields for universe filtering."}),
        encoding="utf-8",
    )
    return root


def _candidates(tmp_path: Path) -> Path:
    path = tmp_path / "test_only_candidates.csv"
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=["factor_id", "name", "formula", "category", "required_fields", "direction"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "factor_id": GOOD,
                "name": "One-Month Reversal",
                "formula": "-(close_t / close_{t-22} - 1)",
                "category": "price_momentum",
                "required_fields": "close;date;code",
                "direction": "negative_reversal",
            }
        )
        writer.writerow({"factor_id": BAD, "name": "Momentum 20"})
        writer.writerow({"factor_id": STUCK, "name": "RSI 6"})
        writer.writerow({"factor_id": NEVER_RUN, "name": "Alpha 002"})
    return path


def test_only_catalog_reports_real_status_and_never_invents_metadata(tmp_path: Path) -> None:
    rows = build_factor_catalog(_candidates(tmp_path), results_root=_results_root(tmp_path))
    by_id = {row["factor_id"]: row for row in rows}

    assert list(by_id) == [GOOD, BAD, STUCK, NEVER_RUN]
    assert by_id[GOOD]["status"] == "validated"
    assert by_id[GOOD]["formula"] == "-(close_t / close_{t-22} - 1)"
    assert by_id[GOOD]["reason"] == ""
    assert by_id[BAD]["status"] == "rejected"
    assert by_id[BAD]["failed_gates"] == "rank_ic"
    assert "minimum_abs_mean" in by_id[BAD]["reason"]
    assert by_id[STUCK]["status"] == "needs_human"
    assert "Missing fields" in by_id[STUCK]["reason"]
    assert by_id[NEVER_RUN]["status"] == "not_run"
    assert "no validation result" in by_id[NEVER_RUN]["reason"]
    # metadata the candidate list does not carry stays empty; nothing is invented
    assert by_id[NEVER_RUN]["category"] == ""
    assert by_id[NEVER_RUN]["direction"] == ""
    for row in rows:
        assert list(row) == list(CATALOG_COLUMNS)


def test_only_catalog_without_results_reports_not_run(tmp_path: Path) -> None:
    rows = build_factor_catalog(_candidates(tmp_path))

    assert {row["status"] for row in rows} == {"not_run"}
    assert all(row["reason"] for row in rows)


def test_only_package_includes_only_validated_factors(tmp_path: Path) -> None:
    root = _results_root(tmp_path)
    payload = build_delivery_package(
        output_dir=tmp_path / "package",
        results_root=root,
        candidates_path=_candidates(tmp_path),
    )

    assert payload["counts"] == {"included": 1, "excluded": 2, "total_seen": 3}
    assert [item["factor_id"] for item in payload["included_factors"]] == [GOOD]
    assert {item["factor_id"] for item in payload["excluded_factors"]} == {BAD, STUCK}

    package_dir = tmp_path / "package"
    copied = package_dir / "factors" / GOOD / "validation_result.json"
    assert copied.is_file()
    record = payload["included_factors"][0]["artifacts"]["result"]
    assert record["sha256"] == hashlib.sha256(copied.read_bytes()).hexdigest()
    assert not (package_dir / "factors" / BAD).exists()
    assert not (package_dir / "factors" / STUCK).exists()

    catalog = package_dir / "factor_catalog.csv"
    assert catalog.is_file()
    assert payload["factor_catalog_sha256"] == hashlib.sha256(catalog.read_bytes()).hexdigest()
    with catalog.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert [row["status"] for row in rows] == ["validated", "rejected", "needs_human", "not_run"]


def test_only_package_warns_when_nothing_is_validated(tmp_path: Path) -> None:
    root = tmp_path / "runs_bad"
    _write_result(
        root,
        BAD,
        {"status": "rejected", "failed_gates": ["coverage"], "gates": []},
    )

    payload = build_delivery_package(output_dir=tmp_path / "package_empty", results_root=root)

    assert payload["counts"]["included"] == 0
    assert "warning" in payload
    assert "no factor reached status 'validated'" in payload["warning"]


def test_only_package_requires_a_source(tmp_path: Path) -> None:
    with pytest.raises(DeliveryPackagingError):
        build_delivery_package(output_dir=tmp_path / "package")


def test_only_package_script_exit_codes(tmp_path: Path) -> None:
    root = _results_root(tmp_path)
    ok = subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8",
            str(REPO_ROOT / "scripts" / "package_delivery.py"),
            "--results-root",
            str(root),
            "--candidates",
            str(_candidates(tmp_path)),
            "--output-dir",
            str(tmp_path / "package_script"),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert json.loads(ok.stdout)["included_factors"] == [GOOD]

    empty_root = tmp_path / "runs_empty"
    _write_result(
        empty_root,
        BAD,
        {"status": "rejected", "failed_gates": ["coverage"], "gates": []},
    )
    empty = subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8",
            str(REPO_ROOT / "scripts" / "package_delivery.py"),
            "--results-root",
            str(empty_root),
            "--output-dir",
            str(tmp_path / "package_script_empty"),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert empty.returncode == 4, empty.stdout + empty.stderr
    assert "warning" in json.loads(empty.stdout)


def test_only_catalog_script_writes_csv(tmp_path: Path) -> None:
    output = tmp_path / "catalog.csv"
    completed = subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8",
            str(REPO_ROOT / "scripts" / "build_factor_catalog.py"),
            "--candidates",
            str(_candidates(tmp_path)),
            "--results-root",
            str(_results_root(tmp_path)),
            "--output",
            str(output),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["rows"] == 4
    assert payload["counts"] == {"validated": 1, "rejected": 1, "needs_human": 1, "not_run": 1}
    assert output.is_file()


def test_only_index_from_results_root_skips_dirs_without_results(tmp_path: Path) -> None:
    root = _results_root(tmp_path)
    (root / "empty_dir").mkdir()

    index = index_from_results_root(root)

    assert set(index) == {GOOD, BAD, STUCK}


def test_only_write_factor_catalog_creates_parent_dirs(tmp_path: Path) -> None:
    rows = build_factor_catalog(_candidates(tmp_path), results_root=_results_root(tmp_path))
    path = write_factor_catalog(rows, tmp_path / "nested" / "factor_catalog.csv")

    assert path.is_file()
