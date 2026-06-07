from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from research_core.factor_lab.libraries.alpha101 import alpha101_specs
from research_core.factor_lab.registry import export_library_specs
from research_core.factor_lab.runtime import FactorLabWorkspaceConfig
from research_core.factor_lab.validation import export_proof_template


class FactorLabRegistryTest(unittest.TestCase):
    def test_alpha101_catalog_exports_101_specs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = FactorLabWorkspaceConfig(data_root=root / "data", runtime_root=root / "runtime")
            specs = alpha101_specs()

            payload = export_library_specs(config=config, library="alpha101", specs=specs)
            self.assertEqual(payload["count"], 101)

            catalog = json.loads(config.catalog_path("alpha101").read_text(encoding="utf-8"))
            self.assertEqual(catalog["count"], 101)
            self.assertEqual(catalog["items"][0]["factor_name"], "alpha1")
            self.assertEqual(catalog["items"][-1]["factor_name"], "alpha101")

    def test_proof_template_can_be_exported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = FactorLabWorkspaceConfig(data_root=root / "data", runtime_root=root / "runtime")
            path = export_proof_template(config=config, spec=alpha101_specs()[0])
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            self.assertEqual(payload["factor_name"], "alpha1")
            self.assertEqual(payload["status"], "pending")
            self.assertGreaterEqual(len(payload["checks"]), 5)


if __name__ == "__main__":
    unittest.main()
