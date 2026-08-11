from __future__ import annotations

import unittest

from contracts.backtest import BacktestRequest
from research_core.backtest_adapter.custom_engine import CustomEngineAdapter


class FakeRunner:
    def __init__(self):
        self.kwargs = None

    def run(self, **kwargs):
        self.kwargs = kwargs
        return {
            "nav": [
                {"date": "2024-01-02", "nav": 1.0, "benchmark": 1.0, "drawdown": 0.0},
                {"date": "2024-01-03", "nav": 1.1, "benchmark": 1.05, "drawdown": -0.02},
            ],
            "kpis": {
                "total_return": 0.1,
                "annual_return": 0.2,
                "sharpe": 1.5,
                "max_drawdown": -0.02,
                "win_rate": 0.55,
                "volatility": 0.12,
            },
            "accounting": {
                "turnover": 0.25,
                "traded_notional": 500000.0,
                "average_equity": 1000000.0,
                "transaction_count": 12,
                "turnover_convention": "two_sided_notional_over_twice_average_equity",
            },
            "holdings": [
                {"code": "600519", "weight": 0.6},
                {"code": "000001", "weight": 0.4},
            ],
            "trades": [
                {
                    "time": "2024-01-03",
                    "code": "600519",
                    "side": "buy",
                    "qty": 100,
                    "price": 100.0,
                    "fee": 5.0,
                }
            ],
        }


def make_request(**overrides):
    values = {
        "run_id": "run-custom-1",
        "strategy_id": "dividend-v6",
        "strategy_version": "v6",
        "strategy_params": {"strategy_name": "红利策略v6(聚宽对齐)", "rebalance_freq": 20},
        "module_path": "engine://chenxi",
        "start_time": "2024-01-01",
        "end_time": "2024-12-31",
        "benchmark": "000300.SH",
        "initial_cash": 1_000_000.0,
        "slippage_bps": 10.0,
        "commission_bps": 3.0,
        "execution_engine": "chenxi",
    }
    values.update(overrides)
    return BacktestRequest(**values)


class CustomEngineAdapterTest(unittest.TestCase):
    def test_maps_legacy_payload_to_agentmatrix_contract(self):
        runner = FakeRunner()
        result = CustomEngineAdapter(runner=runner).run(make_request())

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.engine, "chenxi_engine")
        self.assertAlmostEqual(result.metrics.max_drawdown, 0.02)
        self.assertAlmostEqual(result.metrics.benchmark_return, 0.05)
        self.assertAlmostEqual(result.metrics.turnover, 0.25)
        self.assertEqual(result.equity_curve[-1].drawdown, -0.02)
        self.assertEqual(result.trades[0].symbol, "600519.SH")
        self.assertEqual(result.trades[0].side, "BUY")
        self.assertEqual(result.holdings[0].weights, {"600519.SH": 0.6, "000001.SZ": 0.4})
        self.assertEqual(result.diagnostics["accounting"]["transaction_count"], 12)

        self.assertAlmostEqual(runner.kwargs["fee_rate"], 0.0003)
        self.assertAlmostEqual(runner.kwargs["slippage"], 0.001)
        self.assertEqual(runner.kwargs["rebalance_freq"], 20)

    def test_rejects_non_positive_rebalance_frequency(self):
        request = make_request(strategy_params={"rebalance_freq": 0})
        with self.assertRaisesRegex(ValueError, "rebalance_freq"):
            CustomEngineAdapter(runner=FakeRunner()).run(request)

    def test_requires_engine_root_without_injected_runner(self):
        request = make_request(strategy_params={})
        with self.assertRaisesRegex(ValueError, "AGENTMATRIX_CHENXI_ENGINE_ROOT"):
            CustomEngineAdapter().run(request)


if __name__ == "__main__":
    unittest.main()
