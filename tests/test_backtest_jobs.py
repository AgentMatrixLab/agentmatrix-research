from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.strategy_dashboard_api import create_app
from research_core.backtest_jobs import BacktestJobService, BacktestJobStore, JobRequestError


def registry(path: Path) -> Path:
    target = path / "registry.json"
    target.write_text(json.dumps({"schema_version": 1, "strategies": [{"strategy_id": "s1", "name": "策略一", "version": "v1", "owner": "team", "status": "review", "engine": "chenxi", "benchmark": "000300.SH", "start_date": "2024-01-01", "initial_cash": 1000000, "commission_bps": 3, "slippage_bps": 10, "parameters": {"rebalance_freq": 20}, "quality_gates": {}}]}), encoding="utf-8")
    return target


class BacktestJobsTest(unittest.TestCase):
    def test_persistent_queue_claims_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); store = BacktestJobStore(root / "jobs.db")
            store.create("job-1", {"strategy_id": "s1"})
            claimed = store.claim_next()
            self.assertEqual(claimed["status"], "running")
            self.assertIsNone(store.claim_next())
            self.assertEqual(BacktestJobStore(root / "jobs.db").get("job-1")["status"], "running")

    def test_validates_registry_and_parameter_bounds(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); service = BacktestJobService(BacktestJobStore(root / "jobs.db"), registry(root))
            request = service.validate_request({"strategy_id": "s1", "start_date": "2024-01-01", "end_date": "2024-12-31", "rebalance_freq": 5})
            self.assertEqual(request["benchmark"], "000300.SH")
            with self.assertRaises(JobRequestError):
                service.validate_request({"strategy_id": "unknown"})
            with self.assertRaises(JobRequestError):
                service.validate_request({"strategy_id": "s1", "initial_cash": 1})

    def test_api_is_disabled_by_default_and_accepts_authorized_job(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); reg = registry(root)
            env = {"BACKTEST_JOB_DB": str(root / "jobs.db"), "STRATEGY_REGISTRY_FILE": str(reg)}
            with patch.dict("os.environ", env, clear=False):
                app = create_app(result_dir=root)
                with app.test_client() as client:
                    denied = client.post("/api/strategy-dashboard/backtest-jobs", json={"strategy_id": "s1"})
                    self.assertEqual(denied.status_code, 403)
            enabled = {**env, "BACKTEST_SUBMISSION_ENABLED": "1", "BACKTEST_SUBMISSION_TOKEN": "secret"}
            with patch.dict("os.environ", enabled, clear=False):
                app = create_app(result_dir=root)
                with app.test_client() as client:
                    accepted = client.post("/api/strategy-dashboard/backtest-jobs", headers={"X-Backtest-Token": "secret"}, json={"strategy_id": "s1", "start_date": "2024-01-01", "end_date": "2024-12-31"})
                    self.assertEqual(accepted.status_code, 202)
                    job_id = accepted.get_json()["job_id"]
                    self.assertEqual(client.get(f"/api/strategy-dashboard/backtest-jobs/{job_id}").get_json()["status"], "queued")


if __name__ == "__main__":
    unittest.main()
