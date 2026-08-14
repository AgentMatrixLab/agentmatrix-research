from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from contracts.backtest import ExternalSimulationRequest
from registry.factor_registry.lifecycle import build_promotion_record, validate_transition
from research_core.backtest_adapter.external_simulation import package_external_simulation, parse_external_simulation_result
import research_core.data_loader.amazingdata as amazingdata_module
from research_core.data_loader.amazingdata import (
    AmazingDataConfig,
    build_data_quality_report,
    check_connection,
    fetch_amazingdata_panel,
    normalize_price_panel,
)
from research_core.factor_lab.internal_validation import summarize_internal_validation
from research_core.factor_lab.runtime import FactorLabWorkspaceConfig
import research_core.factor_lab.service as factor_lab_service
from research_core.factor_lab.service import run_factor_set_research_job
from research_core.strategy_engine.alpha_strategy import build_alpha_strategy_package, build_target_weights


class FakeClickHouseClient:
    def __init__(self):
        self.selection_params = []
        self.selection_sql = ""
        self.fetch_sql = ""

    def execute(self, sql, params=None):
        if "SELECT 1" in sql:
            return [(1,)]
        if "countDistinct(trade_date)" in sql:
            return [(4,)]
        if "SELECT k.symbol" in sql:
            self.selection_sql = sql
            self.selection_params.append(params or {})
            return [("000001.SZ",), ("000002.SZ",)]
        if "SELECT" in sql and "trade_date AS date" in sql:
            self.fetch_sql = sql
            dates = pd.date_range("2024-01-01", periods=5, freq="B")
            rows = []
            for code, base in [("000001.SZ", 10.0), ("000002.SZ", 20.0)]:
                for i, date in enumerate(dates):
                    close = base + i
                    rows.append((date.date(), code, close - 0.1, close + 0.2, close - 0.3, close, 1000 + i, close * (1000 + i)))
            return rows
        raise AssertionError(f"Unexpected SQL: {sql}")


def test_amazingdata_fake_client_fetch_and_quality(monkeypatch):
    monkeypatch.setattr(amazingdata_module, "resolve_market_universe", lambda universe: ["000001", "000002", "000003"])
    config = AmazingDataConfig(user="readonly", password="secret")
    client = FakeClickHouseClient()
    assert check_connection(config, client=client)["ok"] is True
    panel, quality = fetch_amazingdata_panel(
        start="2024-01-01",
        end="2024-01-05",
        config=config,
        client=client,
        max_symbols=2,
        warmup_calendar_days=0,
    )
    assert list(panel.columns) == ["date", "code", "open", "high", "low", "close", "volume", "amount", "vwap"]
    assert quality.status == "passed"
    assert quality.n_codes == 2
    assert "universe_symbols" in client.selection_params[0]
    assert "000001.SZ" in client.selection_params[0]["universe_symbols"]
    assert "ods_security_status_daily" in client.selection_sql
    assert "st.is_listed = 1" in client.selection_sql
    assert "s.is_listed = 1" not in client.selection_sql
    assert "ods_security_status_daily" in client.fetch_sql


def test_normalize_price_panel_drops_duplicates_and_flags_missing():
    raw = pd.DataFrame(
        [
            {"trade_date": "2024-01-01", "symbol": "000001.SZ", "close": 10.0},
            {"trade_date": "2024-01-01", "symbol": "000001.SZ", "close": 11.0},
        ]
    )
    panel = normalize_price_panel(raw)
    assert len(panel) == 1
    quality = build_data_quality_report(panel)
    assert quality.status == "failed"
    assert any(issue.check == "schema" for issue in quality.issues)


def test_internal_validation_reports_red_flags_on_weak_factor():
    dates = pd.date_range("2024-01-01", periods=30, freq="B")
    records = []
    for code, base in [("a", 10.0), ("b", 20.0), ("c", 30.0), ("d", 40.0)]:
        for i, date in enumerate(dates):
            records.append({"date": date, "code": code, "close": base + i})
    panel = pd.DataFrame(records)
    factor_frame = panel[["date", "code"]].copy()
    factor_frame["constant_factor"] = 1.0
    report = summarize_internal_validation(panel, factor_frame, factor_names=["constant_factor"])
    flags = report["factors"]["constant_factor"]["red_flags"]
    assert flags


def test_factor_set_demo_job_emits_new_artifacts(tmp_path):
    workspace = FactorLabWorkspaceConfig(data_root=tmp_path / "data", runtime_root=tmp_path / "runtime")
    job = run_factor_set_research_job(
        {
            "factor_set": "wq101",
            "factor_names": ["alpha1"],
            "data_source": "demo",
            "n_dates": 80,
            "n_codes": 8,
            "seed": 42,
        },
        config=workspace,
    )
    assert Path(job["artifacts"]["data_quality_json"]).exists()
    assert Path(job["artifacts"]["internal_validation_json"]).exists()
    assert job["dataset"]["data_source"] == "demo"


def test_amazingdata_validation_trims_warmup_window(tmp_path, monkeypatch):
    workspace = FactorLabWorkspaceConfig(data_root=tmp_path / "data", runtime_root=tmp_path / "runtime")
    dates = pd.date_range("2023-12-20", "2024-01-12", freq="B")
    records = []
    for code_idx in range(6):
        code = f"00000{code_idx + 1}.SZ"
        base = 10.0 + code_idx
        for i, date in enumerate(dates):
            close = base + i * 0.1
            records.append(
                {
                    "date": date,
                    "code": code,
                    "open": close - 0.05,
                    "high": close + 0.10,
                    "low": close - 0.10,
                    "close": close,
                    "volume": 10_000 + i,
                    "amount": close * (10_000 + i),
                    "vwap": close,
                }
            )
    full_panel = pd.DataFrame(records)

    def fake_fetch_amazingdata_panel(**kwargs):
        return full_panel.copy(), build_data_quality_report(full_panel, source="amazingdata")

    monkeypatch.setattr(factor_lab_service, "fetch_amazingdata_panel", fake_fetch_amazingdata_panel)
    job = run_factor_set_research_job(
        {
            "factor_set": "wq101",
            "factor_names": ["alpha1"],
            "data_source": "amazingdata",
            "start": "2024-01-02",
            "end": "2024-01-08",
            "universe": "csi800",
        },
        config=workspace,
    )

    frame = pd.read_csv(job["artifacts"]["factor_frame"])
    assert frame["date"].min() == "2024-01-02"
    assert frame["date"].max() == "2024-01-08"
    assert job["dataset"]["warmup_rows"] > 0
    evaluation = json.loads(Path(job["artifacts"]["evaluation_json"]).read_text(encoding="utf-8"))
    assert evaluation["dataset"]["dates"] == 5


def test_lifecycle_transition_requires_approval_for_live_ready():
    validate_transition("implemented", "internal_validated")
    record = build_promotion_record(
        factor_name="alpha1",
        from_state="implemented",
        to_state="internal_validated",
        promoted_by="test",
    )
    assert record.to_state == "internal_validated"
    try:
        build_promotion_record(
            factor_name="alpha1",
            from_state="external_sim_passed",
            to_state="live_ready",
            promoted_by="test",
        )
    except ValueError as exc:
        assert "approvals" in str(exc)
    else:
        raise AssertionError("live_ready should require approval evidence")


def test_long_short_targets_do_not_overlap_when_top_n_exceeds_half_universe():
    scores = pd.DataFrame(
        {
            "date": ["2024-01-02"] * 6,
            "code": [f"stock_{idx}" for idx in range(6)],
            "alpha_score": [6, 5, 4, 3, 2, 1],
        }
    )
    targets = build_target_weights(scores, as_of="2024-01-02", top_n=5, long_short=True)
    assert not targets.duplicated(["date", "code"]).any()
    long_codes = set(targets.loc[targets["side"] == "long", "code"])
    short_codes = set(targets.loc[targets["side"] == "short", "code"])
    assert long_codes.isdisjoint(short_codes)
    assert len(long_codes) == 3
    assert len(short_codes) == 3


def test_strategy_and_external_package_from_validated_run(tmp_path):
    workspace = FactorLabWorkspaceConfig(data_root=tmp_path / "data", runtime_root=tmp_path / "runtime")
    job = run_factor_set_research_job(
        {
            "factor_set": "wq101",
            "factor_names": ["alpha1"],
            "data_source": "demo",
            "n_dates": 80,
            "n_codes": 8,
            "seed": 7,
        },
        config=workspace,
    )
    strategy = build_alpha_strategy_package(validated_run_path=workspace.job_path(job["job_id"]), top_n=3)
    signal_path = strategy["artifacts"]["signals"]
    signals = pd.read_csv(signal_path)
    assert signals["date"].nunique() > 1
    request = ExternalSimulationRequest(
        run_id="sim-smoke",
        engine="gm",
        strategy_id=strategy["strategy_id"],
        strategy_version="v1",
        signal_path=signal_path,
        start_time="2024-01-01",
        end_time="2024-12-31",
    )
    package = package_external_simulation(request, output_dir=tmp_path / "sim")
    assert Path(package.artifacts["strategy_script"]).exists()
    assert package.diagnostics["signal_dates"] == signals["date"].nunique()
    assert "previous_target_codes" in Path(package.artifacts["strategy_script"]).read_text(encoding="utf-8")
    result_path = tmp_path / "result.json"
    result_path.write_text(json.dumps({"total_return": 0.1, "sharpe": 1.2}), encoding="utf-8")
    parsed = parse_external_simulation_result(run_id="sim-smoke", engine="gm", result_path=result_path)
    assert parsed.metrics.sharpe == 1.2
