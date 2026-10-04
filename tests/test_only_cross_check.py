"""TEST-ONLY tests for the D5 cross-check: it must catch every seeded inconsistency.

The fixture mimics a batch run's artifacts. One clean case must produce zero findings; each
corrupted case must produce exactly the finding it deserves.
"""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from research_core.factor_lab.cross_check import CrossCheckError, cross_check
from research_core.factor_lab.deterministic_validation import (
    _canonical_json,
    _json_safe,
    _report_markdown,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
CODE_COMMIT = "a" * 40
GOOD = "reversal_1m"
BAD = "momentum_20"


def _payload(factor_id: str, status: str, failed: list[str]) -> dict[str, Any]:
    gates = [
        {"name": "coverage", "passed": True, "actual": {"mean_daily_coverage": 0.99}, "threshold": {"minimum_daily_ratio": 0.95}},
        {"name": "rank_ic", "passed": status == "validated", "actual": {"horizon": 10, "mean": 0.02 if status == "validated" else 0.001, "t_stat": 2.5, "ic_ir": 0.3, "days": 400, "yearly": {}}, "threshold": {"minimum_abs_mean": 0.01, "minimum_abs_t_stat": 1.65}},
        {"name": "oos_seal", "passed": True, "actual": {}, "threshold": {}},
        {"name": "style_r2", "passed": True, "actual": {"mean": 0.2}, "threshold": {"maximum_mean": 0.8}},
        {"name": "residual_ic", "passed": True, "actual": {"retention": 0.7}, "threshold": {"minimum_retention": 0.5}},
        {"name": "cost_adjusted_return", "passed": True, "actual": {"net_annualized": 0.05}, "threshold": {"minimum_annualized": 0.0}},
        {"name": "dd_vol_ratio", "passed": True, "actual": {"dd_vol_ratio": 1.0}, "threshold": {"maximum": 3.0}},
        {"name": "parameter_perturbation", "passed": True, "actual": {}, "threshold": {}},
    ]
    return {
        "status": status,
        "requested_factor": factor_id,
        "factor_id": factor_id,
        "fallback_reason": None,
        "release_classification": "internal_preview",
        "license_checked": False,
        "data": {
            "provider": "local_panel_parquet",
            "universe": "all_a",
            "frequency": "1d",
            "adjust_type": "post",
            "eligible_rows": 1000,
            "eligible_codes": 30,
            "eligible_dates": 500,
        },
        "training": {"direction": 1.0, "primary_rank_ic_mean": 0.02, "statistics_scope": ["2016-01-01", "2017-12-31"]},
        "rank_ic": {
            "5d": {"mean": 0.015, "ic_ir": 0.2, "t_stat": 2.0, "days": 400, "yearly": {}},
            "10d": {"mean": 0.02, "ic_ir": 0.3, "t_stat": 2.5, "days": 400, "yearly": {}},
            "20d": {"mean": 0.025, "ic_ir": 0.35, "t_stat": 2.8, "days": 400, "yearly": {}},
        },
        "style": {"fields": ["size"], "r2_mean": 0.2, "residual_ic": {}, "retention": 0.7},
        "portfolio": {"net_annualized": 0.05, "dd_vol_ratio": 1.0},
        "perturbation": {"0.8": {"window": 18, "rank_ic_mean": 0.019, "sign_matches": True}},
        "gates": gates,
        "failed_gates": failed,
    }


def _result_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(_json_safe(payload, precision=12)).encode("utf-8")).hexdigest()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _clean_fixture(tmp_path: Path) -> dict[str, Path]:
    root = tmp_path / "runs"
    root.mkdir(parents=True, exist_ok=True)

    panel = tmp_path / "test_only_panel.parquet"
    factor = tmp_path / "test_only_factor.parquet"
    panel.write_bytes(b"test-only-panel-bytes")
    factor.write_bytes(b"test-only-factor-bytes")

    candidates = tmp_path / "test_only_candidates.csv"
    with candidates.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["factor_id", "name"])
        writer.writeheader()
        writer.writerow({"factor_id": GOOD, "name": "One-Month Reversal"})
        writer.writerow({"factor_id": BAD, "name": "Momentum 20"})

    entries: list[dict[str, Any]] = []
    for factor_id, status, failed in ((GOOD, "validated", []), (BAD, "rejected", ["rank_ic"])):
        directory = root / factor_id
        directory.mkdir(parents=True, exist_ok=True)
        payload = _payload(factor_id, status, failed)
        result_path = directory / "validation_result.json"
        result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        report_path = directory / "validation_report.md"
        report_path.write_text(_report_markdown(payload), encoding="utf-8")
        manifest_path = directory / "run_manifest.json"
        manifest_path.write_text(
            json.dumps({"result_hash": _result_hash(payload), "code_commit": CODE_COMMIT}, indent=2),
            encoding="utf-8",
        )
        entry = {
            "factor_id": factor_id,
            "status": status,
            "failed_gates": failed,
            "reason": "" if status == "validated" else "failed_gate=rank_ic",
            "metadata": {},
            "result_hash": _result_hash(payload),
            "params_hash": "b" * 64,
            "artifacts": {
                "result": str(result_path),
                "manifest": str(manifest_path),
                "report": str(report_path),
            },
        }
        entry["artifact_sha256"] = {
            name: _sha256(Path(path)) for name, path in entry["artifacts"].items()
        }
        entries.append(entry)

    summary_path = tmp_path / "batch_summary.csv"
    with summary_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["factor_id", "status", "result_hash"])
        writer.writeheader()
        for entry in entries:
            writer.writerow(
                {
                    "factor_id": entry["factor_id"],
                    "status": entry["status"],
                    "result_hash": entry["result_hash"],
                }
            )

    manifest = {
        "batch_id": "test_only_batch",
        "created_at_utc": "2026-10-03T00:00:00Z",
        "code_commit": CODE_COMMIT,
        "segment": "oos",
        "candidates_file": candidates.name,
        "candidates_file_sha256": _sha256(candidates),
        "candidate_count": 2,
        "factor_ids": [GOOD, BAD],
        "panel_file": panel.name,
        "panel_file_sha256": _sha256(panel),
        "factor_file": factor.name,
        "factor_file_sha256": _sha256(factor),
        "counts": {"validated": 1, "rejected": 1, "train_only": 0, "needs_human": 0, "error": 0},
        "validated": [GOOD],
        "rejected": [BAD],
        "errors": [],
        "needs_human": [],
        "results": entries,
        "outputs": {"batch_summary_csv": str(summary_path), "batch_summary_sha256": _sha256(summary_path)},
    }
    manifest_path = tmp_path / "batch_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "manifest": manifest_path,
        "panel": panel,
        "factor": factor,
        "candidates": candidates,
        "summary": summary_path,
        "root": root,
    }


def _run(fixture: dict[str, Path], **overrides):
    return cross_check(
        batch_manifest=fixture["manifest"],
        panel_file=fixture["panel"],
        factor_file=fixture["factor"],
        candidates_path=fixture["candidates"],
        **overrides,
    )


def test_only_clean_fixture_has_no_findings(tmp_path: Path) -> None:
    fixture = _clean_fixture(tmp_path)

    payload = _run(fixture)

    assert payload["finding_count"] == 0, payload["findings"]
    assert payload["code_commit"] == CODE_COMMIT
    assert payload["checked"]["result_hash"] == 2


def test_only_cross_check_requires_a_manifest(tmp_path: Path) -> None:
    with pytest.raises(CrossCheckError):
        cross_check(batch_manifest=tmp_path / "missing.json")


def test_only_detects_a_tampered_result_payload(tmp_path: Path) -> None:
    fixture = _clean_fixture(tmp_path)
    result_path = fixture["root"] / GOOD / "validation_result.json"
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    payload["rank_ic"]["10d"]["mean"] = 0.099
    result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    findings = _run(fixture)["findings"]

    checks = {(item["scope"], item["check"]) for item in findings}
    assert (GOOD, "result_hash") in checks
    assert (GOOD, "result_artifact_sha256") in checks
    # the old report still shows the old number, so it must disagree with the result
    assert (GOOD, "report_rank_ic_values") in checks


def test_only_detects_a_tampered_summary_row(tmp_path: Path) -> None:
    fixture = _clean_fixture(tmp_path)
    with fixture["summary"].open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    rows[0]["status"] = "rejected"
    with fixture["summary"].open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["factor_id", "status", "result_hash"])
        writer.writeheader()
        writer.writerows(rows)

    findings = _run(fixture)["findings"]

    assert any(item["check"] == "summary_status" and item["scope"] == GOOD for item in findings)


def test_only_detects_wrong_counts_and_lists(tmp_path: Path) -> None:
    fixture = _clean_fixture(tmp_path)
    manifest = json.loads(fixture["manifest"].read_text(encoding="utf-8"))
    manifest["counts"]["validated"] = 2
    manifest["validated"] = [GOOD, BAD]
    fixture["manifest"].write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    findings = _run(fixture)["findings"]

    checks = {item["check"] for item in findings}
    assert "counts" in checks
    assert "factor_list" in checks


def test_only_detects_a_changed_panel_file(tmp_path: Path) -> None:
    fixture = _clean_fixture(tmp_path)
    fixture["panel"].write_bytes(b"panel-bytes-changed-after-the-run")

    findings = _run(fixture)["findings"]

    assert any(item["check"] == "panel_sha256" for item in findings)


def test_only_detects_a_catalog_status_mismatch(tmp_path: Path) -> None:
    fixture = _clean_fixture(tmp_path)
    catalog = tmp_path / "factor_catalog.csv"
    with catalog.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["factor_id", "status"])
        writer.writeheader()
        writer.writerow({"factor_id": GOOD, "status": "validated"})
        writer.writerow({"factor_id": BAD, "status": "validated"})

    findings = _run(fixture, factor_catalog=catalog)["findings"]

    assert any(item["check"] == "catalog_status" and item["scope"] == BAD for item in findings)


def test_only_detects_a_package_that_ships_a_rejected_factor(tmp_path: Path) -> None:
    fixture = _clean_fixture(tmp_path)
    package_root = tmp_path / "package"
    (package_root / "factors" / BAD).mkdir(parents=True)
    copied = package_root / "factors" / BAD / "validation_result.json"
    copied.write_bytes((fixture["root"] / BAD / "validation_result.json").read_bytes())
    package_manifest = package_root / "package_manifest.json"
    package_manifest.write_text(
        json.dumps(
            {
                "included_factors": [
                    {"factor_id": GOOD, "artifacts": {}},
                    {
                        "factor_id": BAD,
                        "artifacts": {
                            "result": {
                                "path": str(copied.relative_to(package_root)).replace("\\", "/"),
                                "source": str(fixture["root"] / BAD / "validation_result.json"),
                            }
                        },
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    findings = _run(fixture, package_manifest=package_manifest)["findings"]

    assert any(item["check"] == "package_included" for item in findings)


def test_only_cross_check_script_exit_codes(tmp_path: Path) -> None:
    fixture = _clean_fixture(tmp_path)
    base = [
        sys.executable,
        "-X",
        "utf8",
        str(REPO_ROOT / "scripts" / "cross_check_delivery.py"),
        "--batch-manifest",
        str(fixture["manifest"]),
        "--panel-file",
        str(fixture["panel"]),
        "--factor-file",
        str(fixture["factor"]),
        "--candidates",
        str(fixture["candidates"]),
    ]
    clean = subprocess.run(base, cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8")
    assert clean.returncode == 0, clean.stdout + clean.stderr
    assert json.loads(clean.stdout)["finding_count"] == 0

    fixture["factor"].write_bytes(b"tampered")
    dirty = subprocess.run(base, cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8")
    assert dirty.returncode == 5, dirty.stdout + dirty.stderr
    assert json.loads(dirty.stdout)["finding_count"] >= 1
