from __future__ import annotations

import importlib
import json
import tempfile
import unittest
from pathlib import Path

from research_core.factor_lab.demo_data import build_alpha101_demo_panel
from research_core.factor_lab.libraries.alpha101 import compute_alpha101_factors
from research_core.factor_lab.service import (
    export_alpha101_truth_template,
    get_alpha101_factor_detail,
    get_factor_lab_job,
    get_factor_lab_overview,
    list_alpha101_factors,
    list_factor_set_factors,
    run_factor_set_research_job,
    run_alpha101_research_job,
    run_alpha101_truth_proof_batch,
    validate_alpha101_truth_csv,
)
from research_core.factor_lab.runtime import FactorLabWorkspaceConfig


def _gtja_runtime_available() -> bool:
    try:
        importlib.import_module("alpha.context")
    except ImportError:
        return False
    return True


GTJA_RUNTIME_AVAILABLE = _gtja_runtime_available()


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

    def test_run_alpha101_research_job_with_truth_comparison_passes_proof(self) -> None:
        workspace = self._workspace()
        panel = build_alpha101_demo_panel(n_dates=80, n_codes=6, seed=19)
        truth_frame = compute_alpha101_factors(panel, factor_names=["alpha1", "alpha2"])
        truth_csv_path = workspace.data_root / "alpha101_truth.csv"
        truth_csv_path.parent.mkdir(parents=True, exist_ok=True)
        truth_frame.to_csv(truth_csv_path, index=False, encoding="utf-8")

        job = run_alpha101_research_job(
            {
                "factor_names": ["alpha1", "alpha2"],
                "n_dates": 80,
                "n_codes": 6,
                "seed": 19,
                "data_source": "demo",
                "truth_csv_path": str(truth_csv_path),
                "truth_tolerance": 1e-12,
            },
            workspace,
        )

        proof_payload = json.loads(Path(job["artifacts"]["proofs"]["alpha1"]).read_text(encoding="utf-8"))
        self.assertEqual(proof_payload["status"], "passed")
        truth_check = next(item for item in proof_payload["checks"] if item["name"] == "cross_section_truth_compare")
        self.assertEqual(truth_check["status"], "passed")

        truth_compare_path = Path(job["artifacts"]["truth_compares"]["alpha1"])
        self.assertTrue(truth_compare_path.exists())
        truth_payload = json.loads(truth_compare_path.read_text(encoding="utf-8"))
        self.assertEqual(truth_payload["exact_match_ratio"], 1.0)

        self.assertEqual(job["truth_summary"]["factor_count"], 2)
        self.assertEqual(job["truth_summary"]["rows"], len(truth_frame))

        report_json_path = Path(job["artifacts"]["research_report_json"])
        report_payload = json.loads(report_json_path.read_text(encoding="utf-8"))
        self.assertEqual(report_payload["summary"]["proof_status_counts"]["passed"], 2)
        self.assertEqual(report_payload["summary"]["truth_status_counts"]["exact_match"], 2)

        report_path = Path(job["artifacts"]["research_report_markdown"])
        self.assertTrue(report_path.exists())

    def test_export_alpha101_truth_template_writes_csv_and_manifest(self) -> None:
        workspace = self._workspace()
        payload = export_alpha101_truth_template(
            {
                "factor_names": ["alpha1", "alpha2"],
                "n_dates": 40,
                "n_codes": 4,
                "seed": 23,
                "template_name": "alpha101_truth_schema_example",
            },
            workspace,
        )

        csv_path = Path(payload["truth_csv_path"])
        manifest_path = Path(payload["manifest_path"])
        self.assertTrue(csv_path.exists())
        self.assertTrue(manifest_path.exists())

        header = csv_path.read_text(encoding="utf-8").splitlines()[0]
        self.assertEqual(header, "date,code,alpha1,alpha2")

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["summary"]["factor_count"], 2)
        self.assertEqual(manifest["schema"]["required_columns"], ["date", "code", "alpha1", "alpha2"])

    def test_run_alpha101_truth_proof_batch_returns_aggregate_summary(self) -> None:
        workspace = self._workspace()
        template = export_alpha101_truth_template(
            {
                "factor_names": ["alpha1", "alpha2"],
                "n_dates": 80,
                "n_codes": 6,
                "seed": 31,
                "template_name": "alpha101_truth_batch_test",
            },
            workspace,
        )

        payload = run_alpha101_truth_proof_batch(
            {
                "factor_names": ["alpha1", "alpha2"],
                "truth_csv_path": template["truth_csv_path"],
                "truth_tolerance": 1e-12,
                "n_dates": 80,
                "n_codes": 6,
                "seed": 31,
            },
            workspace,
        )

        summary = payload["proof_batch_summary"]
        self.assertEqual(summary["overall_status"], "passed")
        self.assertTrue(summary["ready_for_official_proof"])
        self.assertEqual(summary["proof_status_counts"]["passed"], 2)
        self.assertEqual(summary["truth_status_counts"]["exact_match"], 2)
        self.assertEqual(summary["failed_factors"], [])
        self.assertEqual(summary["truth_blocker_factors"], [])

    def test_validate_alpha101_truth_csv_reports_duplicates(self) -> None:
        workspace = self._workspace()
        truth_csv_path = workspace.data_root / "alpha101_truth_invalid.csv"
        truth_csv_path.parent.mkdir(parents=True, exist_ok=True)
        truth_csv_path.write_text(
            "\n".join(
                [
                    "date,code,alpha1,alpha2",
                    "2020-01-02,000001.SZ,0.1,0.2",
                    "2020-01-02,000001.SZ,0.1,0.2",
                    "2020-01-03,000002.SZ,0.3,0.4",
                ]
            ),
            encoding="utf-8",
        )

        payload = validate_alpha101_truth_csv(
            {
                "factor_names": ["alpha1", "alpha2"],
                "truth_csv_path": str(truth_csv_path),
            },
            workspace,
        )
        validation = payload["validation"]
        self.assertFalse(validation["valid"])
        self.assertEqual(validation["duplicate_key_count"], 2)
        self.assertEqual(validation["empty_factors"], [])

    @unittest.skipUnless(GTJA_RUNTIME_AVAILABLE, "GTJA191 optional runtime dependency is not installed")
    def test_run_gtja191_factor_set_job_exports_formal_chain_artifacts(self) -> None:
        workspace = self._workspace()
        job = run_factor_set_research_job(
            {
                "factor_set": "gtja191",
                "factor_names": ["alpha1", "alpha2"],
                "n_dates": 80,
                "n_codes": 6,
                "seed": 43,
                "data_source": "demo",
            },
            workspace,
        )

        self.assertEqual(job["status"], "completed")
        self.assertEqual(job["library"], "GTJA191")
        self.assertTrue(Path(job["artifacts"]["specs"]).exists())
        self.assertTrue(Path(job["artifacts"]["catalog"]).exists())
        self.assertTrue(Path(job["artifacts"]["factor_frame"]).exists())
        self.assertTrue(Path(job["artifacts"]["evaluation_json"]).exists())
        self.assertTrue(Path(job["artifacts"]["research_report_json"]).exists())
        self.assertTrue(Path(job["artifacts"]["research_report_markdown"]).exists())
        self.assertTrue(Path(job["artifacts"]["proofs"]["alpha1"]).exists())

        catalog = json.loads(Path(job["artifacts"]["catalog"]).read_text(encoding="utf-8"))
        self.assertEqual(catalog["count"], 191)
        self.assertEqual(catalog["items"][0]["library"], "GTJA191")

        items = list_factor_set_factors("gtja191", workspace)
        self.assertEqual(len(items), 191)
        self.assertEqual(items[0]["proof_status"], "partial")


if __name__ == "__main__":
    unittest.main()
