import tempfile
import unittest
from pathlib import Path

from backend.factor_lab_api import (
    _decide_truth_comparison_status,
    _enter_intake_gate,
    _locked_intake_criteria,
    _sha256_file,
    _verify_locked_criteria,
    _write_json,
)


class FactorLabIntakeCriteriaTest(unittest.TestCase):
    def test_truth_not_required_is_not_applicable_and_can_accept(self) -> None:
        criteria = {"truth_required": False}
        result = _decide_truth_comparison_status(criteria, truth_file_present=False)
        self.assertEqual(result["truth_status"], "not_applicable")
        self.assertFalse(result["truth_blocking"])
        self.assertTrue(result["accept_allowed"])

    def test_truth_required_missing_file_is_not_compared_and_blocks(self) -> None:
        criteria = {"truth_required": True}
        result = _decide_truth_comparison_status(criteria, truth_file_present=False)
        self.assertEqual(result["truth_status"], "not_compared")
        self.assertTrue(result["truth_blocking"])
        self.assertFalse(result["accept_allowed"])

    def test_low_overlap_cannot_pass_even_with_exact_matches(self) -> None:
        criteria = {
            "truth_required": True,
            "min_overlap_ratio": 0.9,
            "pass_exact_match_ratio": 0.99,
            "tolerance": 1e-8,
        }
        result = _decide_truth_comparison_status(
            criteria,
            truth_file_present=True,
            overlap_ratio=0.003,
            exact_match_ratio=1.0,
            max_abs_error=0.0,
        )
        self.assertEqual(result["truth_status"], "not_compared")
        self.assertTrue(result["truth_blocking"])
        self.assertFalse(result["accept_allowed"])

    def test_sufficient_overlap_and_exact_match_passes(self) -> None:
        criteria = {
            "truth_required": True,
            "min_overlap_ratio": 0.9,
            "pass_exact_match_ratio": 0.99,
            "tolerance": 1e-8,
        }
        result = _decide_truth_comparison_status(
            criteria,
            truth_file_present=True,
            overlap_ratio=0.95,
            exact_match_ratio=1.0,
            max_abs_error=0.0,
        )
        self.assertEqual(result["truth_status"], "passed")
        self.assertFalse(result["truth_blocking"])
        self.assertTrue(result["accept_allowed"])

    def test_alpha101_criteria_comes_from_registry(self) -> None:
        criteria = _locked_intake_criteria(
            {
                "factor_family": "alpha101",
                "criteria": {"truth_required": False, "tolerance": 999.0},
            },
            "factor_values_compare",
            [{"name": "factor_values.csv"}],
        )
        self.assertTrue(criteria["truth_required"])
        self.assertEqual(criteria["criteria_source"], "registry:alpha101_v1")
        self.assertEqual(criteria["criteria_resolved_at"], "G0")
        self.assertEqual(criteria["initial_truth_decision"]["truth_status"], "not_compared")
        self.assertAlmostEqual(criteria["tolerance"], 1e-8)

    def test_research_reproduction_truth_is_optional_diagnostic(self) -> None:
        criteria = _locked_intake_criteria(
            {
                "factor_family": "unknown_research_family",
                "criteria": {"truth_required": True},
            },
            "research_reproduction",
            [
                {"name": "code.py"},
                {"name": "experiment_data.csv"},
                {"name": "paper.pdf"},
                {"name": "research_report.pdf"},
            ],
        )
        self.assertEqual(criteria["task_type"], "research_reproduction")
        self.assertFalse(criteria["truth_required"])
        self.assertEqual(criteria["standard_truth"]["role"], "optional_diagnostic")
        self.assertFalse(criteria["standard_truth"]["blocking"])
        self.assertEqual(criteria["initial_truth_decision"]["truth_status"], "not_applicable")
        self.assertEqual(criteria["criteria_status"], "resolved")

    def test_research_reproduction_with_truth_file_is_still_non_blocking(self) -> None:
        criteria = _locked_intake_criteria(
            {"factor_family": "alpha101"},
            "research_report_reproduction",
            [
                {"name": "code.py"},
                {"name": "experiment_data.csv"},
                {"name": "paper.pdf"},
                {"name": "research_report.pdf"},
                {"name": "truth_values.csv"},
            ],
        )
        self.assertEqual(criteria["task_type"], "research_reproduction")
        self.assertTrue(criteria["truth_file_present"])
        self.assertFalse(criteria["truth_required"])
        self.assertEqual(criteria["initial_truth_decision"]["truth_status"], "diagnostic_pending")
        self.assertFalse(criteria["initial_truth_decision"]["truth_blocking"])

    def test_unknown_factor_family_fails_safe(self) -> None:
        criteria = _locked_intake_criteria(
            {
                "factor_family": "alpha101_custom",
                "criteria": {"truth_required": False},
            },
            "factor_values_compare",
            [{"name": "factor_values.csv"}],
        )
        self.assertTrue(criteria["truth_required"])
        self.assertEqual(criteria["criteria_status"], "failed")
        self.assertEqual(criteria["criteria_error"], "unknown_factor_family")
        self.assertEqual(criteria["initial_truth_decision"]["truth_status"], "not_compared")

    def test_criteria_hash_detects_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp)
            artifacts_dir = task_dir / "artifacts"
            artifacts_dir.mkdir()
            criteria_path = artifacts_dir / "criteria.json"
            _write_json(criteria_path, {"truth_required": True})
            status = {"criteria_sha256": _sha256_file(criteria_path)}
            self.assertTrue(_verify_locked_criteria(task_dir, status)["ok"])

            _write_json(criteria_path, {"truth_required": False})
            result = _verify_locked_criteria(task_dir, status)
            self.assertFalse(result["ok"])
            self.assertEqual(result["error"], "criteria_tampered")

    def test_gate_entry_rejects_tampered_criteria(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp)
            artifacts_dir = task_dir / "artifacts"
            artifacts_dir.mkdir()
            criteria_path = artifacts_dir / "criteria.json"
            _write_json(criteria_path, {"truth_required": True})
            status = {"criteria_sha256": _sha256_file(criteria_path)}
            self.assertTrue(_enter_intake_gate(task_dir, status, "truth_comparison")["ok"])

            _write_json(criteria_path, {"truth_required": False})
            result = _enter_intake_gate(task_dir, status, "truth_comparison")
            self.assertFalse(result["ok"])
            self.assertEqual(result["error"], "criteria_tampered")


if __name__ == "__main__":
    unittest.main()
