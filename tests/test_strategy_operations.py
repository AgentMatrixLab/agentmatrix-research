from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from contracts.backtest import BacktestResult, EquityPoint, HoldingSnapshot, PerformanceMetrics, TradeRecord
from research_core.strategy_operations import load_registry, validate_result


def result(*, sides=("BUY", "SELL"), end="2026-08-06", turnover=0.2) -> BacktestResult:
    return BacktestResult(
        run_id="run-1", status="completed", engine="custom", strategy_id="s1", strategy_version="v1", benchmark="000300.SH",
        metrics=PerformanceMetrics(0.1, 0.1, 0.03, 0.07, 0.05, 1.0, 0.12, turnover, 0.5),
        equity_curve=[EquityPoint("2026-08-05", 1.0, 1.0, 0.0), EquityPoint(end, 1.1, 1.03, -0.01)],
        trades=[TradeRecord("2026-08-06", "600519.SH", side, 100, 10) for side in sides],
        holdings=[HoldingSnapshot(end, {"600519.SH": 1.0}, {"gross": 1.0})],
    )


class StrategyOperationsTest(unittest.TestCase):
    def test_registry_validates_status_and_runnable_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "registry.json"
            path.write_text(json.dumps({"schema_version": 1, "strategies": [{
                "strategy_id": "s1", "name": "S1", "version": "v1", "owner": "team", "status": "approved",
                "engine": "custom", "benchmark": "000300.SH", "start_date": "2020-01-01", "initial_cash": 1_000_000,
                "commission_bps": 3, "slippage_bps": 10, "parameters": {}, "quality_gates": {}
            }]}), encoding="utf-8")
            self.assertTrue(load_registry(path)[0].runnable)

    def test_quality_gate_accepts_complete_two_sided_result(self):
        report = validate_result(result(), expected_end_date="2026-08-06", gates={"require_two_sided_trades": True})
        self.assertTrue(report.passed)

    def test_quality_gate_rejects_stale_and_one_sided_result(self):
        report = validate_result(result(sides=("BUY",), end="2026-08-05", turnover=0), expected_end_date="2026-08-06", gates={"require_two_sided_trades": True})
        self.assertFalse(report.passed)
        self.assertTrue(any("before data version" in error for error in report.errors))
        self.assertTrue(any("both BUY and SELL" in error for error in report.errors))
        self.assertTrue(any("turnover is zero" in warning for warning in report.warnings))

    def test_quality_gate_rejects_empty_flat_strategy(self):
        empty = result(sides=())
        empty.trades = []
        empty.holdings = []
        empty.equity_curve[1].strategy_nav = 1.0
        report = validate_result(empty, expected_end_date="2026-08-06", gates={
            "require_two_sided_trades": True, "min_trade_count": 1,
            "require_holdings": True, "require_nav_movement": True,
        })
        self.assertFalse(report.passed)
        self.assertIn("strategy NAV is flat", report.errors)
        self.assertIn("holding history is empty", report.errors)

    def test_quality_gate_can_block_zero_turnover(self):
        report = validate_result(result(turnover=0), expected_end_date="2026-08-06", gates={"require_positive_turnover": True})
        self.assertFalse(report.passed)
        self.assertIn("turnover is zero despite non-empty trade history", report.errors)


if __name__ == "__main__":
    unittest.main()
