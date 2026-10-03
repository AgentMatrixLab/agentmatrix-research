"""TEST-ONLY plumbing tests for the precomputed factor-values channel.

Everything here is synthetic or fixture data. Passing these tests proves that reading
precomputed factor values produces exactly the same validation numbers as computing the
same factor through the built-in transform. It is NOT factor-validity evidence.
"""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from research_core.factor_lab.deterministic_validation import (
    _canonical_json,
    _factor_lookup,
    _json_safe,
    execute_validation,
    load_validation_config,
    validate_panel,
)
from research_core.factor_lab.precomputed_factors import (
    PrecomputedFactorError,
    load_precomputed_factors,
    perturbation_factor_name,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "configs" / "validation_gates.yaml"

# The brief fixes the floating-point tolerance for the equivalence check at 1e-10.
FLOAT_TOLERANCE = 1e-10


def _assert_metrics_close(left: object, right: object, path: str = "$") -> None:
    if isinstance(left, dict):
        assert set(left) == set(right), f"key mismatch at {path}: {set(left) ^ set(right)}"
        for key in left:
            _assert_metrics_close(left[key], right[key], f"{path}.{key}")
    elif isinstance(left, list):
        assert len(left) == len(right), f"length mismatch at {path}"
        for index, (item_left, item_right) in enumerate(zip(left, right)):
            _assert_metrics_close(item_left, item_right, f"{path}[{index}]")
    elif isinstance(left, bool) or left is None or right is None:
        assert left == right, f"value mismatch at {path}: {left!r} != {right!r}"
    elif isinstance(left, (int, float)) and isinstance(right, (int, float)):
        assert left == pytest.approx(right, rel=0, abs=FLOAT_TOLERANCE, nan_ok=True), (
            f"numeric mismatch at {path}: {left!r} != {right!r}"
        )
    else:
        assert left == right, f"value mismatch at {path}: {left!r} != {right!r}"


def _synthetic_panel() -> pd.DataFrame:
    """Deterministic, synthetic all-A-shaped panel (TEST ONLY, not market data)."""
    dates = pd.bdate_range("2014-01-02", "2019-12-31")
    codes = [f"{index:06d}.XSHE" for index in range(1, 31)]
    generator = np.random.default_rng(20261003)

    closes = []
    for position, _code in enumerate(codes):
        shocks = generator.normal(0.0004, 0.02, len(dates))
        level = 12.0 + position * 0.35
        closes.append(level * np.exp(np.cumsum(shocks)))
    close = np.concatenate(closes)
    volume = np.concatenate(
        [
            1_000_000.0 + 1_000.0 * position + 10_000.0 * np.abs(np.sin(np.arange(len(dates)) / (7.0 + position)))
            for position in range(len(codes))
        ]
    )

    frame = pd.DataFrame(
        {
            "date": np.tile(dates.to_numpy(), len(codes)),
            "code": np.repeat(codes, len(dates)),
            "close": close,
            "volume": volume,
            "total_turnover": close * volume,
            "limit_up": close * 1.1,
            "limit_down": close * 0.9,
            "circulation_a": 100_000_000.0,
            "listed_date": pd.Timestamp("2010-01-04"),
            "de_listed_date": pd.NaT,
            "is_st": False,
            "is_suspended": False,
        }
    )
    frame["date"] = pd.to_datetime(frame["date"])
    frame["listed_date"] = pd.to_datetime(frame["listed_date"])
    frame["de_listed_date"] = pd.to_datetime(frame["de_listed_date"])
    return frame


def _test_config() -> dict:
    config = copy.deepcopy(load_validation_config(CONFIG_PATH))
    config["split"] = {
        "train_start": "2016-01-01",
        "train_end": "2017-12-31",
        "oos_start": "2018-01-01",
        "oos_end": "2019-12-31",
    }
    return config


def _long_frame(series: pd.Series, factor_name: str) -> pd.DataFrame:
    frame = series.rename("value").reset_index()
    frame["factor_name"] = factor_name
    return frame[["date", "code", "factor_name", "value"]]


def _write_precomputed_file(
    tmp_path: Path,
    panel: pd.DataFrame,
    config: dict,
    *,
    factor_id: str = "reversal_1m",
    include_perturbation: bool = True,
) -> Path:
    """Export the built-in transform's own output, so both channels can be compared."""
    base_window = int(config["factor"]["definitions"][factor_id]["window"])
    frames = [_long_frame(_factor_lookup(panel, factor_id, config), factor_id)]
    if include_perturbation:
        for multiplier in config["perturbation"]["multipliers"]:
            window = max(1, int(round(base_window * float(multiplier))))
            frames.append(
                _long_frame(
                    _factor_lookup(panel, factor_id, config, window=window),
                    perturbation_factor_name(factor_id, window),
                )
            )
    table = pd.concat(frames, ignore_index=True)
    path = tmp_path / "test_only_reversal_1m_factor_values.parquet"
    table.to_parquet(path, index=False)
    metadata = {
        "source": "TEST_ONLY_SYNTHETIC",
        "dataset": "factor_values",
        "data_start": table["date"].min().date().isoformat(),
        "data_end": table["date"].max().date().isoformat(),
        "row_count": int(len(table)),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "factors": {factor_id: {"window": base_window}},
        "value_definition": "TEST_ONLY; equals the built-in negative_pct_change output",
    }
    Path(f"{path}.json").write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
    return path


def _write_test_panel_file(tmp_path: Path, panel: pd.DataFrame) -> Path:
    """Export the synthetic panel in the local validation-panel contract format."""
    path = tmp_path / "test_only_validation_panel.parquet"
    panel.to_parquet(path, index=False)
    metadata = {
        "source": "TEST_ONLY_SYNTHETIC",
        "dataset": "validation_panel",
        "data_start": panel["date"].min().date().isoformat(),
        "data_end": panel["date"].max().date().isoformat(),
        "row_count": int(len(panel)),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "price_basis": "TEST_ONLY; not a production price basis",
    }
    Path(f"{path}.json").write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.fixture(scope="module")
def synthetic_panel() -> pd.DataFrame:
    return _synthetic_panel()

@pytest.fixture(scope="module")
def test_config() -> dict:
    return _test_config()


def test_only_precomputed_channel_reproduces_native_reversal_1m(
    tmp_path: Path, synthetic_panel: pd.DataFrame, test_config: dict
) -> None:
    native_result, native_panel_hash = validate_panel(synthetic_panel, "reversal_1m", test_config)

    path = _write_precomputed_file(tmp_path, synthetic_panel, test_config)
    precomputed = load_precomputed_factors(path)
    precomputed_result, precomputed_panel_hash = validate_panel(
        synthetic_panel, "reversal_1m", test_config, precomputed=precomputed
    )

    provenance = precomputed_result.pop("factor_source", None)
    assert provenance is None, "provenance must not enter the result payload"

    assert native_panel_hash == precomputed_panel_hash
    assert precomputed_result["gates"], "the gate list must still be produced"
    assert precomputed_result["status"] in {"validated", "rejected"}

    _assert_metrics_close(native_result, precomputed_result)
    assert _canonical_json(_json_safe(native_result, precision=12)) == _canonical_json(
        _json_safe(precomputed_result, precision=12)
    ), "precomputed and native result payloads must be identical after 12-digit rounding"


def test_only_precomputed_channel_reproduces_native_train_segment(
    tmp_path: Path, synthetic_panel: pd.DataFrame, test_config: dict
) -> None:
    path = _write_precomputed_file(tmp_path, synthetic_panel, test_config)
    precomputed = load_precomputed_factors(path)

    native_train, _ = validate_panel(synthetic_panel, "reversal_1m", test_config, segment="train")
    precomputed_train, _ = validate_panel(
        synthetic_panel, "reversal_1m", test_config, precomputed=precomputed, segment="train"
    )

    _assert_metrics_close(native_train, precomputed_train)


def test_only_train_segment_never_reports_out_of_sample_statistics(
    synthetic_panel: pd.DataFrame, test_config: dict
) -> None:
    oos_result, _ = validate_panel(synthetic_panel, "reversal_1m", test_config)
    train_result, _ = validate_panel(synthetic_panel, "reversal_1m", test_config, segment="train")

    assert train_result["status"] == "train_only"
    assert train_result["segment"] == "train"
    assert train_result["scope"] == ["2016-01-01", "2017-12-31"]
    assert train_result["gates"] == []
    assert train_result["failed_gates"] == []
    for absent in ("rank_ic", "style", "portfolio", "perturbation", "oos_seal"):
        assert absent not in train_result, f"train segment must not expose {absent}"

    assert train_result["training"]["primary_rank_ic_mean"] == pytest.approx(
        oos_result["training"]["primary_rank_ic_mean"], rel=0, abs=FLOAT_TOLERANCE
    )
    assert train_result["training"]["direction"] == oos_result["training"]["direction"]


def test_only_execute_validation_records_factor_provenance_in_the_manifest(
    tmp_path: Path, synthetic_panel: pd.DataFrame, test_config: dict
) -> None:
    config = copy.deepcopy(test_config)
    config["output"] = dict(config["output"])
    config["output"]["root"] = str(tmp_path / "runs")
    config_path = tmp_path / "test_only_validation_gates.yaml"
    config_path.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8")

    factor_file = _write_precomputed_file(tmp_path, synthetic_panel, test_config)

    native = execute_validation(
        "reversal_1m",
        config_path=config_path,
        panel=synthetic_panel,
        source_metadata={"provider": "test_only_synthetic"},
    )
    precomputed_run = execute_validation(
        "reversal_1m",
        config_path=config_path,
        panel=synthetic_panel,
        source_metadata={"provider": "test_only_synthetic"},
        factor_file=factor_file,
        segment="oos",
    )

    assert native["manifest"]["factor_source"] == "pipeline_transform"
    assert precomputed_run["manifest"]["factor_source"] == "precomputed_parquet"
    assert precomputed_run["manifest"]["segment"] == "oos"
    assert (
        precomputed_run["manifest"]["factor_file_sha256"]
        == hashlib.sha256(factor_file.read_bytes()).hexdigest()
    )
    assert native["manifest"]["result_hash"] == precomputed_run["manifest"]["result_hash"]

    report_path = Path(precomputed_run["artifacts"]["report"])
    assert report_path.is_file()
    assert report_path.read_text(encoding="utf-8").startswith("status=")
    assert Path(precomputed_run["artifacts"]["result"]).is_file()
    assert Path(precomputed_run["artifacts"]["manifest"]).is_file()

    train_run = execute_validation(
        "reversal_1m",
        config_path=config_path,
        panel=synthetic_panel,
        source_metadata={"provider": "test_only_synthetic"},
        factor_file=factor_file,
        segment="train",
    )
    assert train_run["manifest"]["segment"] == "train"
    assert train_run["status"] == "train_only"
    assert "train" in Path(train_run["artifacts"]["result"]).parts
    assert Path(train_run["artifacts"]["result"]).parent != Path(
        precomputed_run["artifacts"]["result"]
    ).parent


def test_only_cli_runs_fully_offline_from_panel_and_factor_files(
    tmp_path: Path, synthetic_panel: pd.DataFrame, test_config: dict
) -> None:
    """The exact command Hermes is expected to run on the server, minus real data."""
    config = copy.deepcopy(test_config)
    config["output"] = dict(config["output"])
    config["output"]["root"] = str(tmp_path / "runs")
    config_path = tmp_path / "test_only_cli_gates.yaml"
    config_path.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8")

    panel_file = _write_test_panel_file(tmp_path, synthetic_panel)
    factor_file = _write_precomputed_file(tmp_path, synthetic_panel, test_config)

    completed = subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8",
            "-m",
            "research_core.factor_lab.cli",
            "validate",
            "--factor",
            "reversal_1m",
            "--config",
            str(config_path),
            "--panel-file",
            str(panel_file),
            "--factor-file",
            str(factor_file),
            "--segment",
            "oos",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["status"] in {"validated", "rejected"}
    assert payload["manifest"]["factor_source"] == "precomputed_parquet"
    assert payload["manifest"]["segment"] == "oos"
    assert payload["manifest"]["panel_file_sha256"] == hashlib.sha256(panel_file.read_bytes()).hexdigest()
    assert payload["manifest"]["factor_file_sha256"] == hashlib.sha256(factor_file.read_bytes()).hexdigest()
    assert payload["manifest"]["panel_price_basis"]
    assert Path(payload["artifacts"]["manifest"]).is_file()


def test_only_missing_perturbation_variant_fails_instead_of_passing_the_gate(    tmp_path: Path, synthetic_panel: pd.DataFrame, test_config: dict
) -> None:
    path = _write_precomputed_file(tmp_path, synthetic_panel, test_config, include_perturbation=False)
    precomputed = load_precomputed_factors(path)

    with pytest.raises(PrecomputedFactorError, match="parameter_perturbation"):
        validate_panel(synthetic_panel, "reversal_1m", test_config, precomputed=precomputed)


def test_only_require_reports_a_missing_factor(
    tmp_path: Path, synthetic_panel: pd.DataFrame, test_config: dict
) -> None:
    path = _write_precomputed_file(tmp_path, synthetic_panel, test_config)
    precomputed = load_precomputed_factors(path)

    with pytest.raises(PrecomputedFactorError, match="alpha002"):
        precomputed.require("alpha002")


def _long_table() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2023-01-03", "2023-01-03", "2023-01-04", "2023-01-04"]),
            "code": ["000001.XSHE", "000002.XSHE", "000001.XSHE", "000002.XSHE"],
            "factor_name": ["reversal_1m", "reversal_1m", "reversal_1m", "reversal_1m"],
            "value": [0.1, np.nan, 0.2, 0.3],
        }
    )


def _write_long_table(tmp_path: Path, table: pd.DataFrame, **sidecar_overrides) -> Path:
    path = tmp_path / "test_only_factor_values.parquet"
    table.to_parquet(path, index=False)
    metadata = {
        "source": "TEST_ONLY_SYNTHETIC",
        "dataset": "factor_values",
        "data_start": pd.to_datetime(table["date"]).min().date().isoformat(),
        "data_end": pd.to_datetime(table["date"]).max().date().isoformat(),
        "row_count": int(len(table)),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "factors": {"reversal_1m": {"window": 22}},
        "value_definition": "TEST_ONLY",
    }
    metadata.update(sidecar_overrides)
    Path(f"{path}.json").write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
    return path


def test_only_loads_valid_long_table_and_keeps_nan_values(tmp_path: Path) -> None:
    path = _write_long_table(tmp_path, _long_table())

    loaded = load_precomputed_factors(path)

    assert loaded.factor_names == ("reversal_1m",)
    series = loaded.require("reversal_1m")
    assert len(series) == 4
    assert np.isnan(series.iloc[1])
    assert loaded.base_window("reversal_1m") == 22
    assert loaded.coverage_span() == (pd.Timestamp("2023-01-03").date(), pd.Timestamp("2023-01-04").date())


def test_only_rejects_parquet_hash_mismatch(tmp_path: Path) -> None:
    path = _write_long_table(tmp_path, _long_table())
    with path.open("ab") as stream:
        stream.write(b"changed after sidecar")

    with pytest.raises(PrecomputedFactorError, match="SHA-256"):
        load_precomputed_factors(path)


def test_only_rejects_missing_required_column(tmp_path: Path) -> None:
    path = _write_long_table(tmp_path, _long_table().drop(columns=["value"]))

    with pytest.raises(PrecomputedFactorError, match="value"):
        load_precomputed_factors(path)


def test_only_rejects_unexpected_extra_column(tmp_path: Path) -> None:
    table = _long_table().assign(note="extra")
    path = _write_long_table(tmp_path, table)

    with pytest.raises(PrecomputedFactorError, match="note"):
        load_precomputed_factors(path)


def test_only_rejects_duplicate_date_code_factor_name(tmp_path: Path) -> None:
    table = pd.concat([_long_table(), _long_table().iloc[[0]]], ignore_index=True)
    path = _write_long_table(tmp_path, table)

    with pytest.raises(PrecomputedFactorError, match="duplicate"):
        load_precomputed_factors(path)


def test_only_rejects_non_numeric_value(tmp_path: Path) -> None:
    table = _long_table()
    table["value"] = ["0.1", "0.2", "0.3", "0.4"]
    path = _write_long_table(tmp_path, table)

    with pytest.raises(PrecomputedFactorError, match="numeric"):
        load_precomputed_factors(path)


def test_only_rejects_non_finite_value(tmp_path: Path) -> None:
    table = _long_table()
    table.loc[0, "value"] = np.inf
    path = _write_long_table(tmp_path, table)

    with pytest.raises(PrecomputedFactorError, match="non-finite"):
        load_precomputed_factors(path)


def test_only_rejects_undeclared_factor_name(tmp_path: Path) -> None:
    table = _long_table()
    table.loc[0, "factor_name"] = "not_declared"
    path = _write_long_table(tmp_path, table)

    with pytest.raises(PrecomputedFactorError, match="not_declared"):
        load_precomputed_factors(path)


def test_only_rejects_declared_factor_without_rows(tmp_path: Path) -> None:
    path = _write_long_table(
        tmp_path,
        _long_table(),
        factors={"reversal_1m": {"window": 22}, "alpha002": {"window": 10}},
    )

    with pytest.raises(PrecomputedFactorError, match="no rows"):
        load_precomputed_factors(path)


def test_only_rejects_sidecar_date_range_mismatch(tmp_path: Path) -> None:
    path = _write_long_table(tmp_path, _long_table(), data_start="2023-01-02")

    with pytest.raises(PrecomputedFactorError, match="date range"):
        load_precomputed_factors(path)


def test_only_rejects_row_count_mismatch(tmp_path: Path) -> None:
    path = _write_long_table(tmp_path, _long_table(), row_count=99)

    with pytest.raises(PrecomputedFactorError, match="row_count mismatch"):
        load_precomputed_factors(path)


def test_only_rejects_missing_sidecar(tmp_path: Path) -> None:
    path = tmp_path / "test_only_missing_sidecar.parquet"
    _long_table().to_parquet(path, index=False)

    with pytest.raises(PrecomputedFactorError, match="sidecar file does not exist"):
        load_precomputed_factors(path)


def test_only_rejects_expected_range_mismatch(tmp_path: Path) -> None:
    path = _write_long_table(tmp_path, _long_table())

    with pytest.raises(PrecomputedFactorError, match="expected_start mismatch"):
        load_precomputed_factors(path, expected_start="2023-01-02")
