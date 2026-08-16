from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from research_core.strategy_operations.dataset_validation import validate_dataset


class StrategyDatasetValidationTest(unittest.TestCase):
    def test_missing_manifest_is_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            report = validate_dataset(Path(directory), verify_hashes=False)
            self.assertEqual(report["status"], "blocked")
            self.assertIn("manifest.json is missing", report["errors"])


if __name__ == "__main__":
    unittest.main()
