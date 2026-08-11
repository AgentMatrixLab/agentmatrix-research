from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from scripts.build_chenxi_compatibility_dataset import build


class ChenxiCompatibilityDatasetTest(unittest.TestCase):
    def test_builds_legacy_dividend_view_without_mutating_base(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base, output = root / "base", root / "output"
            base.mkdir()
            pd.DataFrame({"symbol": ["000001.SZ"], "date": ["2026-01-02"], "dividend_yield": [0.03]}).to_parquet(base / "dividend_yield_2026.parquet", index=False)
            dates = pd.date_range("2025-10-01", periods=70, freq="B")
            pd.DataFrame({
                "symbol": ["000001.SZ"] * len(dates),
                "trade_date": dates,
                "close_adj": [10.0 + index for index in range(len(dates))],
            }).to_parquet(base / "kline_adj.parquet", index=False)
            (base / "manifest.json").write_text(json.dumps({"data_version": "2026-01-02", "base_version": "2025-12-31", "details": {}}), encoding="utf-8")
            manifest = build(base, output)
            self.assertFalse((base / "dividend_yield.parquet").exists())
            result = pd.read_parquet(output / "dividend_yield.parquet")
            self.assertEqual(result.loc[0, "div_yield"], 0.03)
            kline = pd.read_parquet(output / "kline_adj.parquet")
            self.assertTrue({"ret_5d", "ret_60d", "volatility_20d"}.issubset(kline.columns))
            self.assertFalse(pd.isna(kline.iloc[-1]["ret_60d"]))
            self.assertFalse((base / "kline_adj.parquet").stat().st_size == 0)
            self.assertIn("dividend_yield.parquet", manifest["files"])
            self.assertEqual(
                manifest["details"]["kline_adj.parquet"]["signal_features"],
                ["ret_5d", "ret_60d", "volatility_20d"],
            )


if __name__ == "__main__":
    unittest.main()
