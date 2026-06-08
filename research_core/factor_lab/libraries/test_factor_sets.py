from __future__ import annotations

import unittest

import pandas as pd

from research_core.factor_lab.demo_data import build_alpha101_demo_panel
from research_core.factor_lab.libraries.alpha101 import compute_alpha101_factors
from research_core.factor_lab.libraries.factor_sets import (
    WQ101_ALPHA_1_10,
    compute_factor_set,
    compute_gtja191_alphas,
    compute_wq101_alphas,
)
from research_core.factor_lab.libraries.gtja191 import IMPLEMENTED_GTJA191_FACTORS


class FactorSetComputeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.panel = build_alpha101_demo_panel(n_dates=120, n_codes=6, seed=41)

    def _assert_factor_frame(self, frame: pd.DataFrame, expected_factors: tuple[str, ...]) -> None:
        self.assertEqual(frame.columns.tolist(), ["date", "code", *expected_factors])
        self.assertEqual(len(frame), len(self.panel))
        coverage = frame[list(expected_factors)].notna().sum()
        self.assertTrue((coverage > 0).all(), coverage.to_dict())

    def test_compute_wq101_alphas_matches_factor_lab_alpha101_mainline(self) -> None:
        wq101 = compute_wq101_alphas(self.panel)
        mainline = compute_alpha101_factors(self.panel, factor_names=list(WQ101_ALPHA_1_10))

        self._assert_factor_frame(wq101, WQ101_ALPHA_1_10)
        self.assertTrue(wq101.equals(mainline))
        anchor = wq101[(wq101["date"] == pd.Timestamp("2021-02-04")) & (wq101["code"] == "stock_001")].iloc[0]
        self.assertEqual(anchor["alpha1"], -0.25)
        self.assertAlmostEqual(anchor["alpha10"], 1.0 / 3.0)

    def test_compute_gtja191_alphas_has_expected_columns_coverage_and_anchor(self) -> None:
        gtja191 = compute_gtja191_alphas(self.panel)

        self._assert_factor_frame(gtja191, IMPLEMENTED_GTJA191_FACTORS)
        anchor = gtja191[(gtja191["date"] == pd.Timestamp("2021-02-04")) & (gtja191["code"] == "stock_001")].iloc[0]
        self.assertAlmostEqual(anchor["alpha1"], 0.21320071635561028)
        self.assertAlmostEqual(anchor["alpha10"], 1.0 / 6.0)

    def test_compute_factor_set_dispatches_and_validates_columns(self) -> None:
        subset = compute_factor_set(self.panel, "gtja191", factor_names=["alpha1", "alpha3", "alpha10"])

        self.assertEqual(subset.columns.tolist(), ["date", "code", "alpha1", "alpha3", "alpha10"])
        self.assertTrue((subset[["alpha1", "alpha3", "alpha10"]].notna().sum() > 0).all())
        with self.assertRaises(ValueError):
            compute_factor_set(self.panel, "gtja191", factor_names=["alpha11"])


if __name__ == "__main__":
    unittest.main()
