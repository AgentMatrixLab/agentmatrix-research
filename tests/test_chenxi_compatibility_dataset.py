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
            (base / "manifest.json").write_text(json.dumps({"data_version": "2026-01-02", "base_version": "2025-12-31", "details": {}}), encoding="utf-8")
            manifest = build(base, output)
            self.assertFalse((base / "dividend_yield.parquet").exists())
            result = pd.read_parquet(output / "dividend_yield.parquet")
            self.assertEqual(result.loc[0, "div_yield"], 0.03)
            self.assertIn("dividend_yield.parquet", manifest["files"])


if __name__ == "__main__":
    unittest.main()
