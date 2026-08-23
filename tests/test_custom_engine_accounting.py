from __future__ import annotations

import unittest

from research_core.backtest_adapter.custom_engine.accounting import (
    summarize_legacy_accounting,
)


class CustomEngineAccountingTest(unittest.TestCase):
    def test_uses_complete_absolute_trade_notional_and_average_equity(self):
        summary = summarize_legacy_accounting(
            [
                {"side": "buy", "amount": 200_000},
                {"side": "sell", "shares": 1_000, "price": 100},
            ],
            [1_000_000, 1_100_000],
        )
        self.assertAlmostEqual(summary["traded_notional"], 300_000)
        self.assertAlmostEqual(summary["average_equity"], 1_050_000)
        self.assertAlmostEqual(summary["turnover"], 300_000 / 2_100_000)
        self.assertEqual(summary["transaction_count"], 2)


if __name__ == "__main__":
    unittest.main()
