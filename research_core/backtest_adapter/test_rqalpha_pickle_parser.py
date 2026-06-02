from __future__ import annotations

import pickle
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from research_core.backtest_adapter.rqalpha_pickle_parser import RQAlphaPickleParser


class RQAlphaPickleParserTest(unittest.TestCase):
    def test_parse_sys_analyser_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir) / "result.pkl"
            payload = {
                "sys_analyser": {
                    "summary": {
                        "strategy_name": "demo",
                        "benchmark": "000300.XSHG",
                        "total_returns": 0.18,
                        "annualized_returns": 0.12,
                        "benchmark_total_returns": 0.05,
                        "max_drawdown": 0.08,
                        "sharpe": 1.4,
                        "volatility": 0.21,
                        "turnover": 3.2,
                        "transaction_cost": 1200.0,
                        "starting_cash": "STOCK:1000000.0",
                    },
                    "total_portfolios": pd.DataFrame(
                        {
                            "date": pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"]),
                            "unit_net_value": [1.0, 1.05, 1.18],
                            "total_value": [1000000.0, 1050000.0, 1180000.0],
                            "daily_returns": [0.0, 0.05, 0.1238095238],
                        }
                    ).set_index("date"),
                    "benchmark_portfolios": pd.DataFrame(
                        {
                            "date": pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"]),
                            "unit_net_value": [1.0, 1.02, 1.05],
                        }
                    ).set_index("date"),
                    "stock_positions": pd.DataFrame(
                        {
                            "date": pd.to_datetime(["2024-01-03", "2024-01-03", "2024-01-04"]),
                            "order_book_id": ["000001.XSHE", "600000.XSHG", "000001.XSHE"],
                            "market_value": [500000.0, 300000.0, 700000.0],
                        }
                    ).set_index("date"),
                    "trades": pd.DataFrame(
                        {
                            "datetime": pd.to_datetime(["2024-01-03 15:00:00", "2024-01-04 15:00:00"]),
                            "trading_datetime": pd.to_datetime(["2024-01-03 15:00:00", "2024-01-04 15:00:00"]),
                            "order_book_id": ["000001.XSHE", "600000.XSHG"],
                            "side": ["BUY", "SELL"],
                            "position_effect": ["OPEN", "CLOSE"],
                            "last_quantity": [1000, 800],
                            "last_price": [10.0, 12.0],
                            "commission": [10.0, 12.0],
                            "tax": [0.0, 9.6],
                        }
                    ).set_index("datetime"),
                }
            }
            with target.open("wb") as handle:
                pickle.dump(payload, handle)

            parser = RQAlphaPickleParser(target)
            result = parser.parse(
                run_id="run_rqalpha_demo",
                strategy_id="rqalpha-demo",
                strategy_version="v1",
                benchmark="000300.XSHG",
            )

            self.assertEqual(result.status, "parsed")
            self.assertEqual(result.engine, "rqalpha")
            self.assertAlmostEqual(result.metrics.total_return, 0.18)
            self.assertAlmostEqual(result.metrics.excess_return, 0.13)
            self.assertEqual(len(result.equity_curve), 3)
            self.assertEqual(len(result.trades), 2)
            self.assertEqual(len(result.holdings), 2)
            self.assertTrue(result.attribution is not None)
            self.assertEqual(result.benchmark, "000300.XSHG")


if __name__ == "__main__":
    unittest.main()
