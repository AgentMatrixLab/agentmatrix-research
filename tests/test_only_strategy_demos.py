"""TEST-ONLY tests for the strategy demo builder's honesty guards.

The guards matter more than the numbers: a synthetic backtest that reaches the
published dashboard is indistinguishable from a fabricated result. Synthetic
fixtures only; nothing here is strategy evidence.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_strategy_demos as demos  # noqa: E402


def _write_inputs(tmp_path: Path, source: str) -> dict[str, Path]:
    """A tiny but contract-conforming panel, factor table and one validation run."""
    dates = pd.bdate_range("2024-01-01", periods=40)
    rows = []
    for index, code in enumerate(["000001.XSHE", "600000.XSHG", "300750.XSHE"]):
        close = 10.0 + index + np.arange(len(dates)) * 0.1
        rows.append(
            pd.DataFrame(
                {
                    "date": dates,
                    "code": code,
                    "close": close,
                    "industry": ["bank", "industrial", "battery"][index],
                }
            )
        )
    panel = pd.concat(rows, ignore_index=True)
    panel_path = tmp_path / "panel.parquet"
    panel.to_parquet(panel_path, index=False)
    (tmp_path / "panel.parquet.json").write_text(
        json.dumps({"source": source, "dataset": "validation_panel"}), encoding="utf-8"
    )

    values = panel[["date", "code"]].copy()
    values["factor_name"] = "REH_A"
    values["value"] = np.arange(len(values), dtype=float)
    factor_path = tmp_path / "factors.parquet"
    values.to_parquet(factor_path, index=False)
    (tmp_path / "factors.parquet.json").write_text(
        json.dumps({"source": source, "dataset": "factor_values"}), encoding="utf-8"
    )

    runs = tmp_path / "validation_runs" / "REH_A"
    runs.mkdir(parents=True, exist_ok=True)
    (runs / "validation_result.json").write_text(
        json.dumps(
            {
                "factor_id": "REH_A",
                "failed_gates": [],
                "rank_ic": {"10d": {"mean": 0.02, "ic_ir": 0.5, "t_stat": 4.0, "days": 420, "yearly": {}}},
                "training": {"primary_rank_ic_mean": 0.02},
                "style": {"retention": 0.8},
                "portfolio": {
                    "gross_annualized": 0.15,
                    "net_annualized": 0.09,
                    "mean_turnover": 0.4,
                },
            }
        ),
        encoding="utf-8",
    )
    return {"panel": panel_path, "factors": factor_path, "runs": tmp_path / "validation_runs"}


def _argv(inputs: dict[str, Path], out_dir: Path, *extra: str) -> list[str]:
    return [
        "--panel-file", str(inputs["panel"]),
        "--factor-file", str(inputs["factors"]),
        "--runs-dir", str(inputs["runs"]),
        "--out-dir", str(out_dir),
        "--rebalances", "6",
        *extra,
    ]


# ── guard 1: synthetic must be explicit ─────────────────────────────────

def test_synthetic_input_aborts_without_the_flag(tmp_path: Path) -> None:
    inputs = _write_inputs(tmp_path, "TEST_ONLY_SYNTHETIC")
    with pytest.raises(SystemExit, match="TEST_ONLY_SYNTHETIC"):
        demos.main(_argv(inputs, tmp_path / "out"))


def test_synthetic_input_runs_when_explicitly_allowed(tmp_path: Path) -> None:
    inputs = _write_inputs(tmp_path, "TEST_ONLY_SYNTHETIC")
    out = tmp_path / "out"
    assert demos.main(_argv(inputs, out, "--allow-synthetic")) == 0
    assert (out / "strategies.json").is_file()


# ── guard 2: synthetic must never reach the published dashboard ─────────

def test_synthetic_output_is_refused_in_the_published_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs = _write_inputs(tmp_path, "TEST_ONLY_SYNTHETIC")
    published = tmp_path / "published"
    published.mkdir()
    monkeypatch.setattr(demos, "PUBLISHED_DIR", published.resolve())
    with pytest.raises(SystemExit, match="refusing to write synthetic"):
        demos.main(_argv(inputs, published, "--allow-synthetic"))


# ── provenance is recorded, not implied ─────────────────────────────────

def test_output_is_stamped_synthetic(tmp_path: Path) -> None:
    inputs = _write_inputs(tmp_path, "TEST_ONLY_SYNTHETIC")
    out = tmp_path / "out"
    demos.main(_argv(inputs, out, "--allow-synthetic"))
    payload = json.loads((out / "strategies.json").read_text(encoding="utf-8"))
    assert payload["data_status"] == "synthetic_rehearsal"


def test_real_input_is_stamped_as_a_real_run(tmp_path: Path) -> None:
    inputs = _write_inputs(tmp_path, "RQData FULL")
    out = tmp_path / "out"
    demos.main(_argv(inputs, out))
    payload = json.loads((out / "strategies.json").read_text(encoding="utf-8"))
    assert payload["data_status"] == "real_run"


# ── guard 3: no strategy from rejected factors ──────────────────────────

def test_no_strategy_when_nothing_passes_the_frozen_gates(tmp_path: Path) -> None:
    """A correct outcome on data with no signal, not an error to paper over."""
    inputs = _write_inputs(tmp_path, "RQData FULL")
    result_path = inputs["runs"] / "REH_A" / "validation_result.json"
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    payload["failed_gates"] = ["rank_ic"]
    result_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SystemExit, match="no factor passed every frozen gate"):
        demos.main(_argv(inputs, tmp_path / "out"))


def test_a_missing_sidecar_is_named(tmp_path: Path) -> None:
    inputs = _write_inputs(tmp_path, "RQData FULL")
    (tmp_path / "panel.parquet.json").unlink()
    with pytest.raises(demos.DemoError, match="sidecar not found"):
        demos.main(_argv(inputs, tmp_path / "out"))


# ── helpers ─────────────────────────────────────────────────────────────

def test_composite_scores_rank_cross_sectionally() -> None:
    dates = pd.bdate_range("2024-01-01", periods=3)
    values = pd.DataFrame(
        {
            "date": list(dates) * 3,
            "code": ["A"] * 3 + ["B"] * 3 + ["C"] * 3,
            "factor_name": ["F1"] * 9,
            "value": [1.0, 1.0, 1.0, 2.0, 2.0, 2.0, 3.0, 3.0, 3.0],
        }
    )
    scores = demos.composite_stock_scores(values, ["F1"])
    latest = scores[scores["date"] == dates[-1]].sort_values("score")
    assert list(latest["code"]) == ["A", "B", "C"]
    assert latest["score"].max() == pytest.approx(1.0)


def test_composite_scores_reject_an_unknown_factor() -> None:
    values = pd.DataFrame(
        {"date": [pd.Timestamp("2024-01-01")], "code": ["A"], "factor_name": ["F1"], "value": [1.0]}
    )
    with pytest.raises(demos.DemoError, match="none of the selected factors"):
        demos.composite_stock_scores(values, ["MISSING"])


def test_month_end_dates_returns_calendar_month_ends() -> None:
    dates = pd.Series(pd.bdate_range("2024-01-01", "2024-04-30"))
    ends = demos.month_end_dates(dates)
    assert len(ends) == 4
    assert [d.month for d in ends] == [1, 2, 3, 4]
    assert ends == sorted(ends)


def test_month_end_dates_honours_the_count() -> None:
    dates = pd.Series(pd.bdate_range("2024-01-01", "2024-06-30"))
    assert len(demos.month_end_dates(dates, count=3)) == 3
