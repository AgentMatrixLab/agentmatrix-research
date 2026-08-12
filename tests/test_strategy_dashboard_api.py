from __future__ import annotations

import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from backend.strategy_dashboard_api import create_app


class StrategyDashboardApiTest(unittest.TestCase):
    def test_minimal_production_app(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = {
                "run_id": "run-1", "status": "completed", "engine": "custom", "strategy_id": "s1",
                "strategy_version": "v1", "benchmark": "000300.SH", "metrics": {}, "equity_curve": [],
                "trades": [], "holdings": [], "diagnostics": {"strategy_name": "S1"},
            }
            (root / "s1.json").write_text(json.dumps(payload), encoding="utf-8")
            app = create_app(result_dir=root, publication_status="review")
            with app.test_client() as client:
                health = client.get("/healthz")
                self.assertEqual(health.status_code, 200)
                self.assertEqual(health.get_json()["strategies"], 1)
                health.close()
                strategies = client.get("/api/strategy-dashboard/strategies")
                self.assertEqual(strategies.get_json()[0]["publication_status"], "review")
                strategies.close()
                page = client.get("/quant-desk/")
                self.assertEqual(page.status_code, 200)
                page.close()
                self.assertEqual(client.get("/api/positions?strategyId=s1").status_code, 200)
                self.assertEqual(client.get("/api/trades?strategyId=s1").status_code, 200)
                self.assertEqual(client.get("/api/risk/overview?strategyId=s1").status_code, 200)

    def test_status_endpoint_reports_readiness(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            readiness = root / "readiness.json"
            readiness.write_text(json.dumps({"status": "blocked", "data_version": "2026-08-06", "required_failures": ["index_kline"]}), encoding="utf-8")
            with patch.dict("os.environ", {"STRATEGY_DATA_READINESS_FILE": str(readiness)}):
                app = create_app(result_dir=root)
                with app.test_client() as client:
                    response = client.get("/api/strategy-dashboard/status")
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.get_json()["data"]["required_failures"], ["index_kline"])
                    response.close()


if __name__ == "__main__":
    unittest.main()
