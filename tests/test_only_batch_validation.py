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


def _write_multi_factor_file(
    tmp_path: Path, panel: pd.DataFrame, config: dict, *, include_perturbation: bool = True
) -> Path:
    """Export two factors, each with its required perturbation variants."""
    frames: list[pd.DataFrame] = []
    factors: dict[str, dict[str, int]] = {}
    for factor_id in (FACTOR_ID, SECOND_FACTOR_ID):
        base_window = int(config["factor"]["definitions"][factor_id]["window"])
        factors[factor_id] = {"window": base_window}
        frames.append(_long_frame(_factor_lookup(panel, factor_id, config), factor_id))
        if not include_perturbation:
            continue
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


def _write_candidates(
    tmp_path: Path,
    factor_ids: list[str],
    *,
    risk_exposure: tuple[str, ...] = (),
    windows: dict[str, int] | None = None,
    raw_rows: list[dict[str, str]] | None = None,
) -> Path:
    """Write the ruled 9-column candidate list (接龙10)."""
    fields = [
        "factor_id",
        "name",
        "formula",
        "category",
        "required_fields",
        "direction",
        "status",
        "risk_exposure",
        "window",
    ]
    window_map = windows or {}
    path = tmp_path / "test_only_candidate_list.csv"
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        if raw_rows is not None:
            for row in raw_rows:
                writer.writerow({field: row.get(field, "") for field in fields})
            return path
        for index, factor_id in enumerate(factor_ids):
            writer.writerow(
                {
                    "factor_id": factor_id,
                    "name": f"test only {index}",
                    "formula": "",
                    "category": "test_only",
                    "required_fields": "",
                    "direction": "",
                    "status": "test_only",
                    "risk_exposure": "true" if factor_id in risk_exposure else "false",
                    "window": window_map.get(factor_id, ""),
                }
            )
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


def test_only_candidate_list_parses_risk_exposure_and_window(tmp_path: Path) -> None:
    path = _write_candidates(
        tmp_path,
        [FACTOR_ID, SECOND_FACTOR_ID],
        risk_exposure=(SECOND_FACTOR_ID,),
        windows={FACTOR_ID: 22},
    )

    candidates = load_candidate_list(path)

    assert candidates[0].factor_id == FACTOR_ID
    assert candidates[0].risk_exposure is False
    assert candidates[0].window == 22
    assert candidates[1].risk_exposure is True
    assert candidates[1].window is None


def test_only_candidate_list_rejects_a_bad_risk_exposure_value(tmp_path: Path) -> None:
    path = _write_candidates(
        tmp_path, [FACTOR_ID], raw_rows=[{"factor_id": FACTOR_ID, "risk_exposure": "maybe"}]
    )

    with pytest.raises(BatchValidationError, match="risk_exposure"):
        load_candidate_list(path)


def test_only_candidate_list_rejects_a_non_positive_window(tmp_path: Path) -> None:
    path = _write_candidates(
        tmp_path, [FACTOR_ID], raw_rows=[{"factor_id": FACTOR_ID, "window": "0"}]
    )

    with pytest.raises(BatchValidationError, match="window"):
        load_candidate_list(path)


def test_only_batch_carries_risk_exposure_and_window(
    tmp_path: Path, synthetic_panel: pd.DataFrame, test_config: dict
) -> None:
    config_path = _write_config(tmp_path, test_config)
    panel_file = _write_panel_file(tmp_path, synthetic_panel)
    factor_file = _write_multi_factor_file(tmp_path, synthetic_panel, test_config)
    candidates = _write_candidates(
        tmp_path,
        [FACTOR_ID, SECOND_FACTOR_ID],
        risk_exposure=(SECOND_FACTOR_ID,),
        windows={FACTOR_ID: 22},
    )

    payload = run_batch(
        candidates,
        config_path=config_path,
        panel_file=panel_file,
        factor_file=factor_file,
        segment="oos",
        output_dir=tmp_path / "batch_risk",
    )

    assert payload["risk_exposure_factor_ids"] == [SECOND_FACTOR_ID]
    by_id = {entry["factor_id"]: entry for entry in payload["results"]}
    assert by_id[FACTOR_ID]["risk_exposure"] is False
    assert by_id[FACTOR_ID]["window"] == 22
    assert by_id[SECOND_FACTOR_ID]["risk_exposure"] is True
    assert by_id[SECOND_FACTOR_ID]["window"] is None
    # a risk exposure is never counted as effective alpha, whatever its verdict
    for factor_id in payload["validated_effective_alpha"]:
        assert factor_id != SECOND_FACTOR_ID
    assert payload["counts"]["validated_effective_alpha"] == len(payload["validated_effective_alpha"])
    assert payload["counts"]["validated_risk_exposure"] == len(payload["validated_risk_exposure"])

    summary = pd.read_csv(Path(payload["outputs"]["batch_summary_csv"]), dtype=str, keep_default_na=False)
    assert list(summary["risk_exposure"]) == ["false", "true"]
    assert list(summary["window"]) == ["22", ""]


def test_only_window_conflict_between_csv_and_sidecar_is_isolated(
    tmp_path: Path, synthetic_panel: pd.DataFrame, test_config: dict
) -> None:
    config_path = _write_config(tmp_path, test_config)
    panel_file = _write_panel_file(tmp_path, synthetic_panel)
    factor_file = _write_multi_factor_file(tmp_path, synthetic_panel, test_config)
    candidates = _write_candidates(
        tmp_path,
        [FACTOR_ID, SECOND_FACTOR_ID],
        windows={FACTOR_ID: 22, SECOND_FACTOR_ID: 19},  # sidecar says avg_amount_log window=20
    )

    payload = run_batch(
        candidates,
        config_path=config_path,
        panel_file=panel_file,
        factor_file=factor_file,
        segment="oos",
        output_dir=tmp_path / "batch_window_conflict",
    )

    by_id = {entry["factor_id"]: entry for entry in payload["results"]}
    assert by_id[SECOND_FACTOR_ID]["status"] == "error"
    assert "window" in by_id[SECOND_FACTOR_ID]["reason"]
    assert by_id[FACTOR_ID]["status"] in {"validated", "rejected"}
    assert payload["counts"]["error"] == 1


def test_only_missing_perturbation_variant_is_rejected_not_an_error(
    tmp_path: Path, synthetic_panel: pd.DataFrame, test_config: dict
) -> None:
    """Ruling A+B: unmeasured perturbation must show up as a failed gate, not abort the batch."""
    config_path = _write_config(tmp_path, test_config)
    panel_file = _write_panel_file(tmp_path, synthetic_panel)
    factor_file = _write_multi_factor_file(tmp_path, synthetic_panel, test_config, include_perturbation=False)
    candidates = _write_candidates(tmp_path, [FACTOR_ID])

    payload = run_batch(
        candidates,
        config_path=config_path,
        panel_file=panel_file,
        factor_file=factor_file,
        segment="oos",
        output_dir=tmp_path / "batch_unmeasured",
    )

    entry = payload["results"][0]
    assert entry["status"] == "rejected"
    assert "parameter_perturbation" in entry["failed_gates"]
    assert payload["counts"]["error"] == 0
    result_payload = json.loads(Path(entry["artifacts"]["result"]).read_text(encoding="utf-8"))
    gate = next(item for item in result_payload["gates"] if item["name"] == "parameter_perturbation")
    assert gate["passed"] is False
    assert gate["actual"]["measured"] is False
    assert gate["threshold"]["unmeasured_counts_as"] == "not_passed"


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
