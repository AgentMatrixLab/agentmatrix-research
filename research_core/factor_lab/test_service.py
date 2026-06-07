from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from research_core.factor_lab.service import (
    get_alpha101_factor_detail,
    get_factor_lab_job,
    get_factor_lab_overview,
    list_alpha101_factors,
    run_alpha101_research_job,
)
from research_core.factor_lab.runtime import FactorLabWorkspaceConfig


class FactorLabServiceTest(unittest.TestCase):
    def _workspace(self) -> FactorLabWorkspaceConfig:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        root = Path(temp_dir.name)
        return FactorLabWorkspaceConfig(
            data_root=root / "data",
            runtime_root=root / "runtime",
        )

    def test_overview_and_listing(self) -> None:
        workspace = self._workspace()
        overview = get_factor_lab_overview(workspace)
        self.assertEqual(overview["libraries"][0]["library"], "Alpha101")

        items = list_alpha101_factors(workspace)
        self.assertEqual(len(items), 101)
        self.assertEqual(items[0]["factor_name"], "alpha1")

    def test_run_alpha101_research_job_exports_artifacts(self) -> None:
        workspace = self._workspace()
        job = run_alpha101_research_job(
            {
                "factor_names": ["alpha1", "alpha2"],
                "n_dates": 80,
                "n_codes": 6,
                "seed": 11,
                "data_source": "demo",
            },
            workspace,
        )
        self.assertEqual(job["status"], "completed")
        self.assertTrue(Path(job["artifacts"]["factor_frame"]).exists())
        self.assertTrue(Path(job["artifacts"]["evaluation_json"]).exists())
        self.assertTrue(Path(job["artifacts"]["evaluation_markdown"]).exists())

        proof_path = Path(job["artifacts"]["proofs"]["alpha1"])
        self.assertTrue(proof_path.exists())
        proof_payload = json.loads(proof_path.read_text(encoding="utf-8"))
        self.assertIn(proof_payload["status"], {"partial", "passed"})
        self.assertEqual(proof_payload["checks"][0]["status"], "passed")
        self.assertEqual(proof_payload["checks"][1]["status"], "passed")

        job_payload = get_factor_lab_job(job["job_id"], workspace)
        self.assertIsNotNone(job_payload)
        detail = get_alpha101_factor_detail("alpha1", workspace)
        self.assertEqual(detail["spec"]["factor_name"], "alpha1")
        self.assertIsNotNone(detail["proof"])
        self.assertIsNotNone(detail["sample_checks"])


if __name__ == "__main__":
    unittest.main()
