"""TEST-ONLY tests for the batch entry point.

The candidate list and every factor value here are synthetic fixtures. This proves the batch
driver records failures and keeps going; it is not factor-validity evidence.
"""

from __future__ import annotations

import copy
import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest
import yaml

from research_core.factor_lab.batch_validation import (
    BatchValidationError,
    load_candidate_list,
    run_batch,
)
from research_core.factor_lab.deterministic_validation import _factor_lookup, execute_validation
from research_core.factor_lab.precomputed_factors import perturbation_factor_name

REPO_ROOT = Path(__file__).resolve().parents[1]

FACTOR_ID = "reversal_1m"
SECOND_FACTOR_ID = "avg_amount_log"
MISSING_FACTOR_ID = "alpha002"


def _long_frame(series: pd.Series, factor_name: str) -> pd.DataFrame:
    frame = series.rename("value").reset_index()
    frame["factor_name"] = factor_name
    return frame[["date", "code", "factor_name", "value"]]


def _write_multi_factor_file(tmp_path: Path, panel: pd.DataFrame, config: dict) -> Path:
    """Export two factors, each with its required perturbation variants."""
    frames: list[pd.DataFrame] = []
    factors: dict[str, dict[str, int]] = {}
    for factor_id in (FACTOR_ID, SECOND_FACTOR_ID):
        base_window = int(config["factor"]["definitions"][factor_id]["window"])
        factors[factor_id] = {"window": base_window}
        frames.append(_long_frame(_factor_lookup(panel, factor_id, config), factor_id))
        for multiplier in config["perturbation"]["multipliers"]:
            window = max(1, int(round(base_window * float(multiplier))))
            frames.append(
                _long_frame(
                    _factor_lookup(panel, factor_id, config, window=window),
                    perturbation_factor_name(factor_id, window),
                )
            )
    table = pd.concat(frames, ignore_index=True)
    path = tmp_path / "test_only_batch_factor_values.parquet"
    table.to_parquet(path, index=False)
    metadata = {
        "source": "TEST_ONLY_SYNTHETIC",
        "dataset": "factor_values",
        "data_start": table["date"].min().date().isoformat(),
        "data_end": table["date"].max().date().isoformat(),
        "row_count": int(len(table)),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "factors": factors,
        "value_definition": "TEST_ONLY; equals the built-in transform output",
    }
    Path(f"{path}.json").write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
    return path


def _write_panel_file(tmp_path: Path, panel: pd.DataFrame) -> Path:
    path = tmp_path / "test_only_batch_panel.parquet"
    panel.to_parquet(path, index=False)
    Path(f"{path}.json").write_text(
        json.dumps(
            {
                "source": "TEST_ONLY_SYNTHETIC",
                "dataset": "validation_panel",
                "data_start": panel["date"].min().date().isoformat(),
                "data_end": panel["date"].max().date().isoformat(),
                "row_count": int(len(panel)),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "price_basis": "TEST_ONLY",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def _write_candidates(tmp_path: Path, factor_ids: list[str]) -> Path:
    path = tmp_path / "test_only_candidate_list.csv"
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["factor_id", "name", "category"])
        writer.writeheader()
        for index, factor_id in enumerate(factor_ids):
            writer.writerow({"factor_id": factor_id, "name": f"test only {index}", "category": "test_only"})
    return path


def _write_config(tmp_path: Path, config: dict) -> Path:
    payload = copy.deepcopy(config)
    payload["output"] = dict(payload["output"])
    payload["output"]["root"] = str(tmp_path / "runs")
    path = tmp_path / "test_only_batch_gates.yaml"
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def test_only_candidate_list_requires_factor_id(tmp_path: Path) -> None:
    path = tmp_path / "test_only_bad_candidates.csv"
    path.write_text("name,category\nfoo,bar\n", encoding="utf-8")

    with pytest.raises(BatchValidationError, match="factor_id"):
        load_candidate_list(path)


def test_only_candidate_list_rejects_duplicates(tmp_path: Path) -> None:
    path = _write_candidates(tmp_path, [FACTOR_ID, FACTOR_ID])

    with pytest.raises(BatchValidationError, match="duplicate"):
        load_candidate_list(path)


def test_only_batch_records_a_failure_and_keeps_running(
    tmp_path: Path, synthetic_panel: pd.DataFrame, test_config: dict
) -> None:
    config_path = _write_config(tmp_path, test_config)
    panel_file = _write_panel_file(tmp_path, synthetic_panel)
    factor_file = _write_multi_factor_file(tmp_path, synthetic_panel, test_config)
    candidates = _write_candidates(tmp_path, [FACTOR_ID, MISSING_FACTOR_ID, SECOND_FACTOR_ID])

    payload = run_batch(
        candidates,
        config_path=config_path,
        panel_file=panel_file,
        factor_file=factor_file,
        segment="oos",
        output_dir=tmp_path / "batch",
    )

    assert payload["candidate_count"] == 3
    assert payload["factor_ids"] == [FACTOR_ID, MISSING_FACTOR_ID, SECOND_FACTOR_ID]
    assert payload["counts"]["error"] == 1
    assert payload["errors"] == [MISSING_FACTOR_ID]
    assert payload["counts"]["validated"] + payload["counts"]["rejected"] == 2

    by_id = {entry["factor_id"]: entry for entry in payload["results"]}
    missing = by_id[MISSING_FACTOR_ID]
    assert missing["status"] == "error"
    assert MISSING_FACTOR_ID in missing["reason"]
    for factor_id in (FACTOR_ID, SECOND_FACTOR_ID):
        entry = by_id[factor_id]
        assert entry["status"] in {"validated", "rejected"}
        assert entry["result_hash"]
        assert entry["params_hash"]
        assert Path(entry["artifacts"]["result"]).is_file()
        assert entry["artifact_sha256"]["result"] == hashlib.sha256(
            Path(entry["artifacts"]["result"]).read_bytes()
        ).hexdigest()
        assert entry["metrics"]["rank_ic_mean_primary"] is not None

    manifest = json.loads(Path(payload["batch_manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["panel_file_sha256"] == hashlib.sha256(panel_file.read_bytes()).hexdigest()
    assert manifest["factor_file_sha256"] == hashlib.sha256(factor_file.read_bytes()).hexdigest()
    assert manifest["code_commit"]
    assert len(manifest["code_commit"]) == 40
    assert manifest["parameters"]["split"] == test_config["split"]
    assert manifest["parameters"]["gates"] == test_config["gates"]
    assert manifest["parameters"]["portfolio"]["cost"] == test_config["portfolio"]["cost"]
    assert manifest["segment"] == "oos"
    assert manifest["counts"]["error"] == 1

    summary = pd.read_csv(Path(payload["outputs"]["batch_summary_csv"]), dtype=str, keep_default_na=False)
    assert list(summary["factor_id"]) == [FACTOR_ID, MISSING_FACTOR_ID, SECOND_FACTOR_ID]
    assert list(summary["status"]) == [by_id[FACTOR_ID]["status"], "error", by_id[SECOND_FACTOR_ID]["status"]]

    # Batch and single-factor runs must agree on result_hash, or the D5 cross-check is meaningless.
    single = execute_validation(
        FACTOR_ID,
        config_path=config_path,
        panel_file=panel_file,
        factor_file=factor_file,
        segment="oos",
    )
    assert single["manifest"]["result_hash"] == by_id[FACTOR_ID]["result_hash"]


def test_only_batch_train_segment_reports_no_oos_metrics(
    tmp_path: Path, synthetic_panel: pd.DataFrame, test_config: dict
) -> None:
    config_path = _write_config(tmp_path, test_config)
    panel_file = _write_panel_file(tmp_path, synthetic_panel)
    factor_file = _write_multi_factor_file(tmp_path, synthetic_panel, test_config)
    candidates = _write_candidates(tmp_path, [FACTOR_ID])

    payload = run_batch(
        candidates,
        config_path=config_path,
        panel_file=panel_file,
        factor_file=factor_file,
        segment="train",
        output_dir=tmp_path / "batch_train",
    )

    assert payload["counts"]["train_only"] == 1
    entry = payload["results"][0]
    assert entry["status"] == "train_only"
    assert entry["failed_gates"] == []
    assert entry["metrics"]["net_annualized"] is None
    assert entry["metrics"]["rank_ic_mean_primary"] is not None
    assert "train" in Path(entry["artifacts"]["result"]).parts


def test_only_batch_cli_exits_three_when_a_factor_errors(
    tmp_path: Path, synthetic_panel: pd.DataFrame, test_config: dict
) -> None:
    """Runs the real command line: batch must finish, then report the error via exit code 3."""
    config_path = _write_config(tmp_path, test_config)
    panel_file = _write_panel_file(tmp_path, synthetic_panel)
    factor_file = _write_multi_factor_file(tmp_path, synthetic_panel, test_config)
    candidates = _write_candidates(tmp_path, [FACTOR_ID, MISSING_FACTOR_ID])

    completed = subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8",
            "-m",
            "research_core.factor_lab.cli",
            "validate-batch",
            "--candidates",
            str(candidates),
            "--config",
            str(config_path),
            "--panel-file",
            str(panel_file),
            "--factor-file",
            str(factor_file),
            "--segment",
            "oos",
            "--output-dir",
            str(tmp_path / "batch_cli"),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert completed.returncode == 3, completed.stdout + completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["candidate_count"] == 2
    assert payload["counts"]["error"] == 1
    assert payload["errors"] == [MISSING_FACTOR_ID]
    assert "results" not in payload, "the CLI must not dump every factor's full payload"
    assert Path(payload["batch_manifest_path"]).is_file()
    assert Path(payload["outputs"]["batch_summary_csv"]).is_file()


def test_only_batch_subset_filter(tmp_path: Path, synthetic_panel: pd.DataFrame, test_config: dict) -> None:
    config_path = _write_config(tmp_path, test_config)
    panel_file = _write_panel_file(tmp_path, synthetic_panel)
    factor_file = _write_multi_factor_file(tmp_path, synthetic_panel, test_config)
    candidates = _write_candidates(tmp_path, [FACTOR_ID, SECOND_FACTOR_ID])

    payload = run_batch(
        candidates,
        config_path=config_path,
        panel_file=panel_file,
        factor_file=factor_file,
        segment="train",
        output_dir=tmp_path / "batch_subset",
        factor_ids=[SECOND_FACTOR_ID],
    )

    assert payload["factor_ids"] == [SECOND_FACTOR_ID]
    assert payload["candidate_count"] == 1
