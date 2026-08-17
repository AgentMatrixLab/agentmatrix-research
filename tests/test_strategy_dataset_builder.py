from __future__ import annotations

import unittest

import pandas as pd

from research_core.strategy_operations.dataset_builder import merge_unique, normalize_boolean_matrix, normalize_dividend_yield, normalize_price_frames


class StrategyDatasetBuilderTest(unittest.TestCase):
    def test_normalizes_raw_and_pre_adjusted_prices(self):
        raw = pd.DataFrame({"order_book_id": ["600519.XSHG"], "date": ["2026-08-06"], "open": [10], "high": [11], "low": [9], "close": [10], "volume": [100], "total_turnover": [1000], "limit_up": [11], "limit_down": [9]})
        adjusted = pd.DataFrame({"order_book_id": ["600519.XSHG"], "date": ["2026-08-06"], "open": [8], "high": [8.8], "low": [7.2], "close": [8]})
        result = normalize_price_frames(raw, adjusted)
        self.assertEqual(result.iloc[0]["symbol"], "600519.SH")
        self.assertEqual(result.iloc[0]["close_adj"], 8)

    def test_normalizes_boolean_matrix(self):
        frame = pd.DataFrame({"600519.XSHG": [False]}, index=pd.to_datetime(["2026-08-06"]))
        result = normalize_boolean_matrix(frame, "is_suspended")
        self.assertEqual(result.iloc[0]["symbol"], "600519.SH")
        self.assertEqual(result.iloc[0]["is_suspended"], 0)

    def test_merge_replaces_duplicate_key(self):
        old = pd.DataFrame({"symbol": ["s"], "trade_date": [pd.Timestamp("2026-08-06")], "value": [1]})
        new = old.assign(value=2)
        self.assertEqual(merge_unique(old, new, ["symbol", "trade_date"]).iloc[0]["value"], 2)

    def test_normalizes_legacy_basis_points_to_decimal_yield(self):
        legacy = pd.DataFrame({"order_book_id": ["600519.XSHG", "000001.XSHE"], "date": ["2026-08-06"] * 2, "dividend_yield": [398.2, 0.5]})
        result = normalize_dividend_yield(legacy)
        self.assertAlmostEqual(result.loc[result["symbol"] == "600519.SH", "dividend_yield"].iloc[0], 0.03982)
        self.assertAlmostEqual(result.loc[result["symbol"] == "000001.SZ", "dividend_yield"].iloc[0], 0.00005)
        current = legacy.assign(dividend_yield=[0.03982, 0.00005])
        normalized_current = normalize_dividend_yield(current)
        self.assertAlmostEqual(normalized_current.loc[normalized_current["symbol"] == "600519.SH", "dividend_yield"].iloc[0], 0.03982)


if __name__ == "__main__":
    unittest.main()
