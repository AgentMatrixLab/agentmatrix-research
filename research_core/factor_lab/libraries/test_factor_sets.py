from __future__ import annotations

import importlib
import unittest
from unittest import mock

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


def _gtja_runtime_available() -> bool:
    try:
        importlib.import_module("alpha.context")
    except ImportError:
        return False
    return True


GTJA_RUNTIME_AVAILABLE = _gtja_runtime_available()


class FactorSetComputeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.panel = build_alpha101_demo_panel(n_dates=120, n_codes=6, seed=41)
        self.long_panel = build_alpha101_demo_panel(n_dates=320, n_codes=8, seed=41)

    def _with_real_benchmark_context(self, panel: pd.DataFrame) -> pd.DataFrame:
        enriched = panel.copy()
        dates = sorted(enriched["date"].unique())
        benchmark_close = pd.Series(range(len(dates)), index=dates, dtype=float).add(3000.0)
        benchmark_open = benchmark_close.shift(1).fillna(benchmark_close.iloc[0]).add(0.5)
        enriched["benchmark_index_close"] = enriched["date"].map(benchmark_close)
        enriched["benchmark_index_open"] = enriched["date"].map(benchmark_open)
        return enriched

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

    @unittest.skipUnless(GTJA_RUNTIME_AVAILABLE, "GTJA191 optional runtime dependency is not installed")
    def test_compute_gtja191_alphas_has_expected_columns_coverage_and_anchor(self) -> None:
        gtja191 = compute_gtja191_alphas(self.panel, factor_names=["alpha1", "alpha10"])

        self._assert_factor_frame(gtja191, ("alpha1", "alpha10"))
        anchor = gtja191[(gtja191["date"] == pd.Timestamp("2021-02-04")) & (gtja191["code"] == "stock_001")].iloc[0]
        self.assertAlmostEqual(anchor["alpha1"], 0.21320071635561028)
        self.assertAlmostEqual(anchor["alpha10"], 1.0 / 6.0)

    def test_gtja191_exposes_full_alpha191_catalog(self) -> None:
        expected = tuple(f"alpha{idx}" for idx in range(1, 192))

        self.assertEqual(IMPLEMENTED_GTJA191_FACTORS, expected)

    @unittest.skipUnless(GTJA_RUNTIME_AVAILABLE, "GTJA191 optional runtime dependency is not installed")
    def test_compute_gtja191_supports_late_factor_subset(self) -> None:
        factors = ("alpha11", "alpha100", "alpha191")
        gtja191 = compute_gtja191_alphas(self.long_panel, factor_names=list(factors))

        self._assert_factor_frame(gtja191, factors)
        self.assertEqual(gtja191[["date", "code"]].drop_duplicates().shape[0], len(self.long_panel))

    def test_benchmark_dependent_factor_requires_explicit_market_context(self) -> None:
        with self.assertRaisesRegex(ValueError, "benchmark_index_close"):
            compute_gtja191_alphas(self.long_panel, factor_names=["alpha149"])

    @unittest.skipUnless(GTJA_RUNTIME_AVAILABLE, "GTJA191 optional runtime dependency is not installed")
    def test_benchmark_dependent_factor_uses_explicit_market_context(self) -> None:
        gtja191 = compute_gtja191_alphas(self._with_real_benchmark_context(self.long_panel), factor_names=["alpha149"])

        self.assertEqual(gtja191.columns.tolist(), ["date", "code", "alpha149"])
        self.assertEqual(len(gtja191), len(self.long_panel))

    def test_gtja191_runtime_dependency_is_lazy_and_scoped_to_compute(self) -> None:
        real_import_module = importlib.import_module

        def fail_alpha_context(name: str, *args, **kwargs):
            if name == "alpha.context":
                raise ImportError("missing optional dependency")
            return real_import_module(name, *args, **kwargs)

        with mock.patch("importlib.import_module", side_effect=fail_alpha_context):
            wq101 = compute_factor_set(self.panel, "wq101", factor_names=["alpha1"])
            self.assertEqual(wq101.columns.tolist(), ["date", "code", "alpha1"])
            with self.assertRaisesRegex(ImportError, "optional dependency 'py-alpha-lib'"):
                compute_gtja191_alphas(self.panel, factor_names=["alpha1"])

    @unittest.skipUnless(GTJA_RUNTIME_AVAILABLE, "GTJA191 optional runtime dependency is not installed")
    def test_compute_factor_set_dispatches_and_validates_columns(self) -> None:
        subset = compute_factor_set(self.long_panel, "gtja191", factor_names=["alpha1", "alpha100", "alpha191"])

        self.assertEqual(subset.columns.tolist(), ["date", "code", "alpha1", "alpha100", "alpha191"])
        self.assertTrue((subset[["alpha1", "alpha100", "alpha191"]].notna().sum() > 0).all())
        with self.assertRaises(ValueError):
            compute_factor_set(self.panel, "gtja191", factor_names=["alpha192"])


if __name__ == "__main__":
    unittest.main()
