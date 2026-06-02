from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from contracts.backtest import BacktestRequest
from research_core.backtest_adapter.rqalpha_adapter import RQAlphaBacktestAdapter
from research_core.backtest_adapter.example_rqalpha_plan import SAMPLE_MODULES


class RQAlphaAdapterTest(unittest.TestCase):
    def test_build_execution_plan_from_sample_strategy(self) -> None:
        adapter = RQAlphaBacktestAdapter()
        module_path = Path(__file__).resolve().parents[1] / "strategy_engine" / "samples" / "rqalpha_buy_hold_etf.py"
        request = BacktestRequest(
            run_id="run_plan_demo",
            strategy_id="rqalpha-buy-hold-etf",
            strategy_version="v1",
            strategy_params={"frequency": "1d"},
            module_path=str(module_path),
            start_time="2024-01-01",
            end_time="2024-12-31",
            benchmark="000300.XSHG",
            initial_cash=1000000,
            execution_engine="rqalpha",
        )

        plan = adapter.build_execution_plan(request)

        self.assertEqual(plan["engine"], "rqalpha")
        self.assertIn("init", plan["hooks"])
        self.assertIn("handle_bar", plan["hooks"])
        self.assertEqual(plan["rqalpha_config"]["base"]["benchmark"], "000300.XSHG")
        self.assertEqual(plan["rqalpha_config"]["base"]["accounts"], {"stock": 1000000})
        self.assertTrue(plan["artifact_paths"]["result_pickle"].endswith("result.pkl"))

    def test_build_execution_plan_for_dual_ma_sample(self) -> None:
        adapter = RQAlphaBacktestAdapter()
        module_path = SAMPLE_MODULES["rqalpha_dual_ma_etf"]
        request = BacktestRequest(
            run_id="run_dual_ma_demo",
            strategy_id="rqalpha-dual-ma-etf",
            strategy_version="v1",
            strategy_params={"sample_name": "rqalpha_dual_ma_etf", "frequency": "1d"},
            module_path=str(module_path),
            start_time="2023-01-01",
            end_time="2024-12-31",
            benchmark="000300.XSHG",
            initial_cash=1000000,
            execution_engine="rqalpha",
        )

        plan = adapter.build_execution_plan(request)

        self.assertEqual(plan["engine"], "rqalpha")
        self.assertEqual(plan["rqalpha_config"]["base"]["strategy_file"], str(module_path.resolve()))
        self.assertIn("init", plan["hooks"])
        self.assertIn("handle_bar", plan["hooks"])
        self.assertEqual(plan["rqalpha_config"]["base"]["start_date"], "2023-01-01")
        self.assertEqual(plan["rqalpha_config"]["base"]["end_date"], "2024-12-31")

    def test_build_output_paths_accepts_explicit_targets(self) -> None:
        adapter = RQAlphaBacktestAdapter()
        with tempfile.TemporaryDirectory() as tmp_dir:
            module_path = Path(__file__).resolve()
            pickle_path = Path(tmp_dir) / "custom.pkl"
            report_path = Path(tmp_dir) / "report"
            request = BacktestRequest(
                run_id="run_output_demo",
                strategy_id="rqalpha-demo",
                strategy_version="v1",
                strategy_params={
                    "result_pickle": str(pickle_path),
                    "report_save_path": str(report_path),
                },
                module_path=str(module_path),
                start_time="2024-01-01",
                end_time="2024-12-31",
                benchmark="000300.XSHG",
                initial_cash=1000000,
                execution_engine="rqalpha",
            )

            paths = adapter.build_output_paths(request)

            self.assertEqual(paths["result_pickle"], str(pickle_path))
            self.assertEqual(paths["report_save_path"], str(report_path))


if __name__ == "__main__":
    unittest.main()
