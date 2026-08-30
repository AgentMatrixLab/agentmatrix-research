from __future__ import annotations

import unittest

import numpy as np
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
from research_core.factor_lab.operators import (
    compute_vwap,
    cross_sectional_rank,
    ts_delta,
    ts_max,
)


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

    def test_compute_gtja191_alphas11_20_deterministic_anchors(self) -> None:
        """alpha11-20 新增因子的 value-level 确定性锚点，拦截公式翻译错误。"""
        gtja191 = compute_gtja191_alphas(self.panel)
        anchor = gtja191[(gtja191["date"] == pd.Timestamp("2021-06-10")) & (gtja191["code"] == "stock_001")].iloc[0]

        expected = {
            "alpha11": 3250728.879249573,
            "alpha12": -1.0 / 3.0,
            "alpha13": -0.008687333145712017,
            "alpha14": 0.601369700129954,
            "alpha15": 0.011843391618431731,
            "alpha17": 2.0 / 3.0,
            "alpha18": 1.0518106457316359,
            "alpha19": 0.049258529509935284,
            "alpha20": 5.770063835910197,
        }
        for name, value in expected.items():
            self.assertFalse(np.isnan(anchor[name]), f"{name} anchor is NaN")
            self.assertAlmostEqual(anchor[name], value, msg=name)

    def test_gtja191_alpha17_matches_spec_semantics(self) -> None:
        """alpha17 spec: RANK((VWAP - TSMAX(VWAP,15))^DELTA(CLOSE,5))。

        独立按 spec 复算（先幂再横截面 RANK），与实现逐值比对，
        可拦截"先 RANK 再幂"这类运算顺序错误。
        """
        gtja191 = compute_gtja191_alphas(self.panel)

        vwap = compute_vwap(self.panel)
        max_vwap_15 = ts_max(self.panel.assign(vwap=vwap), "vwap", 15)
        delta_close_5 = ts_delta(self.panel, "close", 5)
        powered = pd.Series(np.power(vwap - max_vwap_15, delta_close_5), index=self.panel.index)
        expected = cross_sectional_rank(self.panel.assign(powered_gap=powered), "powered_gap")

        merged = self.panel[["date", "code"]].assign(expected=expected).merge(gtja191, on=["date", "code"])
        both = merged.dropna(subset=["alpha17", "expected"])
        self.assertGreater(len(both), 0, "alpha17 无可比对的非空值")
        self.assertTrue(np.allclose(both["alpha17"], both["expected"]))

    def test_compute_factor_set_dispatches_and_validates_columns(self) -> None:
        subset = compute_factor_set(self.panel, "gtja191", factor_names=["alpha1", "alpha3", "alpha10"])

        self.assertEqual(subset.columns.tolist(), ["date", "code", "alpha1", "alpha3", "alpha10"])
        self.assertTrue((subset[["alpha1", "alpha3", "alpha10"]].notna().sum() > 0).all())
        with self.assertRaises(ValueError):
            compute_factor_set(self.panel, "gtja191", factor_names=["alpha21"])


if __name__ == "__main__":
    unittest.main()
