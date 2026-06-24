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
        self.long_panel = build_alpha101_demo_panel(n_dates=320, n_codes=8, seed=41)

    def _assert_factor_frame(self, frame: pd.DataFrame, expected_factors: tuple[str, ...]) -> None:
        self.assertEqual(frame.columns.tolist(), ["date", "code", *expected_factors])
        self.assertEqual(frame[["date", "code"]].drop_duplicates().shape[0], len(frame))
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
        gtja191 = compute_gtja191_alphas(self.panel, factor_names=["alpha1", "alpha10"])

        self._assert_factor_frame(gtja191, ("alpha1", "alpha10"))
        anchor = gtja191[(gtja191["date"] == pd.Timestamp("2021-02-04")) & (gtja191["code"] == "stock_001")].iloc[0]
        self.assertAlmostEqual(anchor["alpha1"], 0.21320071635561028)
        self.assertAlmostEqual(anchor["alpha10"], 1.0 / 6.0)

    def test_gtja191_exposes_full_alpha191_catalog(self) -> None:
        expected = tuple(f"alpha{idx}" for idx in range(1, 192))

        self.assertEqual(IMPLEMENTED_GTJA191_FACTORS, expected)

    def test_compute_gtja191_supports_late_factor_subset(self) -> None:
        factors = ("alpha11", "alpha100", "alpha191")
        gtja191 = compute_gtja191_alphas(self.long_panel, factor_names=list(factors))

        self._assert_factor_frame(gtja191, factors)
        self.assertEqual(gtja191[["date", "code"]].drop_duplicates().shape[0], len(self.long_panel))

    def test_benchmark_dependent_factor_is_registered_and_computable(self) -> None:
        gtja191 = compute_gtja191_alphas(self.long_panel, factor_names=["alpha149"])

        self.assertEqual(gtja191.columns.tolist(), ["date", "code", "alpha149"])
        self.assertEqual(len(gtja191), len(self.long_panel))

    def test_compute_factor_set_dispatches_and_validates_columns(self) -> None:
        subset = compute_factor_set(self.long_panel, "gtja191", factor_names=["alpha1", "alpha100", "alpha191"])

        self.assertEqual(subset.columns.tolist(), ["date", "code", "alpha1", "alpha100", "alpha191"])
        self.assertTrue((subset[["alpha1", "alpha100", "alpha191"]].notna().sum() > 0).all())
        with self.assertRaises(ValueError):
            compute_factor_set(self.panel, "gtja191", factor_names=["alpha192"])


if __name__ == "__main__":
    unittest.main()
