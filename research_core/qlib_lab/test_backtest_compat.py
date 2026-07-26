from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd


class _FakeFactorLab:
    def fetch_expression_frame(self, expression: str, start_time: str, end_time: str) -> pd.DataFrame:
        dates = pd.date_range("2024-01-01", periods=4, freq="D")
        instruments = [f"S{i:03d}" for i in range(60)]
        rows = []
        for day_index, date in enumerate(dates):
            for instrument_index, instrument in enumerate(instruments):
                rows.append(
                    {
                        "date": date,
                        "instrument": instrument,
                        "close": 100.0 + instrument_index + day_index,
                        "factor": float(60 - instrument_index),
                    }
                )
        return pd.DataFrame(rows).set_index(["date", "instrument"])


class QlibBacktestCompatTest(unittest.TestCase):
    def test_run_factor_backtest_accepts_legacy_top_k(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            from common import paths
            from research_core.qlib_lab.backtest import run_factor_backtest

            original_runtime_dir = paths.RUNTIME_DIR
            paths.RUNTIME_DIR = Path(tmp_dir)
            try:
                result = run_factor_backtest(
                    _FakeFactorLab(),
                    run_id="run_top_k_demo",
                    strategy_id="adhoc_factor_strategy",
                    strategy_version="v1",
                    benchmark="SH000300",
                    start_time="2024-01-01",
                    end_time="2024-01-04",
                    factor_expression="$close",
                    top_k=10,
                    horizon=1,
                    long_short=False,
                )
            finally:
                paths.RUNTIME_DIR = original_runtime_dir

        self.assertEqual(result.diagnostics["top_k"], 10)
        self.assertEqual(result.diagnostics["top_pct"], 10 / 60)
        self.assertEqual(len(result.holdings), 3)
        self.assertEqual(len(result.holdings[0].weights), 10)


if __name__ == "__main__":
    unittest.main()
