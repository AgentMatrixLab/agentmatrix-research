from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from research_core.factor_lab.deterministic_validation import (
    _rolling_factor,
    execute_validation,
    load_validation_config,
)


ROOT = Path(__file__).resolve().parents[1]


def _synthetic_panel() -> pd.DataFrame:
    config = load_validation_config(ROOT / "configs" / "validation_gates.yaml")
    start = config["data"]["warmup_start"]
    end = config["data"]["validation_end"]
    dates = pd.bdate_range(start, end)
    codes = [f"{index:06d}.XSHE" for index in range(1, 25)]
    rng = np.random.default_rng(20260921)
    rows: list[pd.DataFrame] = []
    for index, code in enumerate(codes):
        innovations = rng.normal(0.0, 0.10, len(dates))
        turnover = np.empty(len(dates))
        turnover[0] = 1.0 + index / len(codes)
        for position in range(1, len(dates)):
            turnover[position] = 0.97 * turnover[position - 1] + 0.03 * (1.0 + index / len(codes)) + innovations[position]
        turnover = np.maximum(turnover, 0.05)
        standardized = (turnover - turnover.mean()) / turnover.std()
        one_day_return = np.r_[0.0, standardized[:-1] * 0.001 + rng.normal(0.0, 0.003, len(dates) - 1)]
        close = (10.0 + index) * np.cumprod(1.0 + one_day_return)
        amount = np.exp(rng.normal(18.0, 0.6, len(dates)))
        rows.append(
            pd.DataFrame(
                {
                    "date": dates,
                    "code": code,
                    "close": close,
                    "volume": amount / close,
                    "total_turnover": amount,
                    "limit_up": close * 1.1,
                    "limit_down": close * 0.9,
                    "circulation_a": 1_000_000_000.0 + index * 10_000_000.0,
                    "turnover_rate": turnover,
                    "listed_date": pd.Timestamp("2000-01-01"),
                    "de_listed_date": pd.NaT,
                    "status": "Active",
                    "is_st": False,
                    "is_suspended": False,
                }
            )
        )
    return pd.concat(rows, ignore_index=True)


def _config_in_tmp(tmp_path: Path, *, output_name: str, coverage_threshold: float | None = None) -> Path:
    config = load_validation_config(ROOT / "configs" / "validation_gates.yaml")
    config["output"]["root"] = str(tmp_path / output_name)
    config["data"]["cache_enabled"] = False
    if coverage_threshold is not None:
        config["gates"]["coverage"]["minimum_daily_ratio"] = coverage_threshold
    path = tmp_path / f"{output_name}.yaml"
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return path


def test_reversal_uses_exact_22_sessions_without_crossing_missing_or_suspended_days() -> None:
    config = load_validation_config(ROOT / "configs" / "validation_gates.yaml")
    dates = pd.bdate_range("2020-01-01", periods=55)
    close = 100.0 * np.cumprod(np.full(len(dates), 1.001))
    rows = []
    for code in ("000001.XSHE", "000002.XSHE"):
        for position, date in enumerate(dates):
            if code == "000001.XSHE" and position == 8:
                continue
            rows.append(
                {
                    "date": date,
                    "code": code,
                    "close": close[position],
                    "is_suspended": code == "000001.XSHE" and position == 24,
                }
            )
    panel = pd.DataFrame(rows)

    signal = _rolling_factor(panel, "reversal_1m", config)
    result = panel.assign(signal=signal)
    first_code = result[result["code"] == "000001.XSHE"].set_index("date")["signal"]

    assert pd.isna(first_code.loc[dates[22]])
    assert pd.isna(first_code.loc[dates[31]])
    assert first_code.loc[dates[47]] == pytest.approx(-(close[47] / close[25] - 1.0))


def test_same_inputs_produce_identical_manifest_hashes(tmp_path: Path) -> None:
    panel = _synthetic_panel()
    config_path = _config_in_tmp(tmp_path, output_name="deterministic")

    first = execute_validation("turnover_20d", config_path=config_path, panel=panel)
    second = execute_validation("turnover_20d", config_path=config_path, panel=panel.copy())

    assert first["status"] in {"validated", "rejected"}
    assert first["manifest"] == second["manifest"]
    assert len(first["manifest"]["data_snapshot_hash"]) == 64
    assert len(first["manifest"]["result_hash"]) == 64
    payload = json.loads(Path(first["artifacts"]["result"]).read_text(encoding="utf-8"))
    gates = {gate["name"]: gate for gate in payload["gates"]}
    assert gates["oos_seal"]["passed"] is True
    assert gates["parameter_perturbation"]["passed"] is True


def test_stricter_gate_rejects_and_names_the_gate(tmp_path: Path) -> None:
    panel = _synthetic_panel()
    config_path = _config_in_tmp(tmp_path, output_name="strict", coverage_threshold=1.01)

    result = execute_validation("turnover_20d", config_path=config_path, panel=panel)

    assert result["status"] == "rejected"
    assert "coverage" in result["failed_gates"]
    report_first_line = Path(result["artifacts"]["report"]).read_text(encoding="utf-8").splitlines()[0]
    assert report_first_line.startswith("status=rejected failed_gate=coverage actual=")


def test_missing_dependency_writes_needs_human(tmp_path: Path) -> None:
    panel = _synthetic_panel().drop(columns=["total_turnover"])
    config_path = _config_in_tmp(tmp_path, output_name="missing")

    result = execute_validation("turnover_20d", config_path=config_path, panel=panel)

    assert result["status"] == "needs_human"
    payload = json.loads(Path(result["artifact"]).read_text(encoding="utf-8"))
    assert payload["status"] == "needs_human"
    assert "total_turnover" in payload["missing_fields"]


def test_external_release_fails_closed_without_license_check(tmp_path: Path) -> None:
    panel = _synthetic_panel()
    config_path = _config_in_tmp(tmp_path, output_name="external")
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["release"]["mode"] = config["release"]["external_mode"]
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    result = execute_validation("turnover_20d", config_path=config_path, panel=panel)

    assert result["status"] == "needs_human"
    payload = json.loads(Path(result["artifact"]).read_text(encoding="utf-8"))
    assert payload["details"] == {"license_checked": False, "release_mode": "external_release"}
