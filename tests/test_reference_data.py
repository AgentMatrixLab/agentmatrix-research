from __future__ import annotations

import unittest

import pandas as pd

from research_core.strategy_operations.reference_data import merge_index_data


class ReferenceDataTest(unittest.TestCase):
    def test_merge_replaces_overlap_and_appends_new_date(self):
        existing = pd.DataFrame({
            "order_book_id": ["000300.XSHG"], "date": ["2026-08-05"], "open": [1], "high": [1], "low": [1],
            "close": [1], "volume": [1], "total_turnover": [1],
        })
        update = pd.DataFrame({
            "order_book_id": ["000300.XSHG", "000300.XSHG"], "date": ["2026-08-05", "2026-08-06"],
            "open": [2, 3], "high": [2, 3], "low": [2, 3], "close": [2, 3], "volume": [2, 3], "total_turnover": [2, 3],
        })
        merged = merge_index_data(existing, update)
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged.iloc[0]["close"], 2)
        self.assertEqual(merged.iloc[-1]["date"].date().isoformat(), "2026-08-06")


if __name__ == "__main__":
    unittest.main()
