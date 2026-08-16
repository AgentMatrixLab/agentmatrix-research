from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from research_core.strategy_operations.readiness import build_readiness_manifest


class DataReadinessTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "kline").mkdir()
        (self.root / "status").mkdir()
        pd.DataFrame({"symbol": ["600519.SH"], "trade_date": ["2026-08-06"], "close": [10.0]}).to_parquet(self.root / "kline" / "2026.parquet", index=False)
        pd.DataFrame({"symbol": ["600519.SH"], "trade_date": ["2026-08-06"], "is_st": [False]}).to_parquet(self.root / "status" / "2026.parquet", index=False)
        self.config = {"data_version_source": "kline", "datasets": [
            {"id": "kline", "glob": "kline/*.parquet", "required_columns": ["symbol", "trade_date", "close"], "date_column": "trade_date", "freshness": "data_version", "required": True},
            {"id": "status", "glob": "status/*.parquet", "required_columns": ["symbol", "trade_date", "is_st"], "date_column": "trade_date", "freshness": "data_version", "required": True},
        ]}

    def tearDown(self):
        self.temp.cleanup()

    def test_ready_when_required_datasets_align(self):
        manifest = build_readiness_manifest(self.root, self.config)
        self.assertEqual(manifest["status"], "ready")
        self.assertEqual(manifest["data_version"], "2026-08-06")

    def test_blocked_when_required_dataset_is_stale(self):
        pd.DataFrame({"symbol": ["600519.SH"], "trade_date": ["2026-08-05"], "is_st": [False]}).to_parquet(self.root / "status" / "2026.parquet", index=False)
        manifest = build_readiness_manifest(self.root, self.config)
        self.assertEqual(manifest["status"], "blocked")
        self.assertIn("status", manifest["required_failures"])

    def test_blocked_when_schema_is_incomplete(self):
        pd.DataFrame({"symbol": ["600519.SH"], "trade_date": ["2026-08-06"]}).to_parquet(self.root / "status" / "2026.parquet", index=False)
        manifest = build_readiness_manifest(self.root, self.config)
        self.assertEqual(manifest["status"], "blocked")
        self.assertTrue(any("missing columns" in error for error in manifest["datasets"][1]["errors"]))


if __name__ == "__main__":
    unittest.main()
