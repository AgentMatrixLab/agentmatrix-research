from __future__ import annotations

import unittest

from research_core.factor_lab.demo_data import build_alpha101_demo_panel
from research_core.factor_lab.libraries.alpha101 import IMPLEMENTED_ALPHA101_FACTORS, alpha101_specs, compute_alpha101_factors


class Alpha101FactorsTest(unittest.TestCase):
    def test_compute_first_10_alpha101_factors(self) -> None:
        panel = build_alpha101_demo_panel(n_dates=100, n_codes=6, seed=7)
        result = compute_alpha101_factors(panel)
        expected_cols = ["date", "code", *IMPLEMENTED_ALPHA101_FACTORS]
        self.assertEqual(result.columns.tolist(), expected_cols)
        self.assertEqual(len(result), len(panel))
        non_null_counts = result[list(IMPLEMENTED_ALPHA101_FACTORS)].notna().sum()
        self.assertTrue((non_null_counts > 0).all())

    def test_specs_mark_first_10_as_implemented(self) -> None:
        spec_map = {spec.factor_name: spec for spec in alpha101_specs()}
        for factor_name in IMPLEMENTED_ALPHA101_FACTORS:
            self.assertEqual(spec_map[factor_name].metadata["status"], "implemented")
            self.assertTrue(spec_map[factor_name].formula)
        self.assertEqual(spec_map["alpha11"].metadata["status"], "planned")


if __name__ == "__main__":
    unittest.main()
