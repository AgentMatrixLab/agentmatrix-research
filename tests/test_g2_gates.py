"""G2 九道闸门骨架测试（mock 数据判别力验证）。

核心断言：**闸门有判别力**——好因子过、坏因子挂且死因正确。
另覆盖：BH-FDR 校正数学正确性、闸门5 过滤全集、逐道短路、OOS 跨账本累计。
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research_core.factor_db.g2_gates import (
    G2_GATE_ORDER,
    _bh_adjusted_pvalue,
    gate5_executability,
    run_g2,
)
from research_core.factor_db.g2_mock_data import PREREG_SPLIT, build_long_panel
from research_core.factor_db.lifecycle import OOSAccessLedger


@pytest.fixture(scope="module")
def panel():
    wide, names = build_long_panel()
    return wide, names


class TestMockPanel:
    def test_panel_shape_and_fields(self, panel):
        wide, names = panel
        # 30 股 × 96 月 = 2880 行
        assert wide["date"].nunique() == 96 and wide["code"].nunique() == 30
        # 33 真名 + 5 预埋
        assert len(names) == 38
        # 闸门5/10 字段齐备
        for col in ("limit_up", "limit_down", "suspended", "is_st",
                    "days_since_ipo", "avg_amount_20d", "log_mcap", "industry", "mom_load"):
            assert col in wide.columns

    def test_qapi33_names_all_present(self, panel):
        _, names = panel
        from research_core.factor_db.metadata import _all_factors

        qapi = [r["factor_id"].split(":", 1)[1] for r in _all_factors() if r["factor_id"].startswith("QAPI33:")]
        assert set(qapi) <= set(names)


class TestGateDiscriminativePower:
    """骨架验证的核心：预埋因子必须死在正确的闸门。"""

    def test_planted_good_passes_all(self, panel):
        wide, _ = panel
        report = run_g2(wide, "planted_good", prereg_split=PREREG_SPLIT)
        assert report.passed_all, [g.reason for g in report.gates if not g.passed]

    def test_planted_decay_dies_at_oos(self, panel):
        wide, _ = panel
        report = run_g2(wide, "planted_decay", prereg_split=PREREG_SPLIT)
        assert report.first_failure == "g8_oos_retention"

    def test_planted_regime_dies_at_segments(self, panel):
        wide, _ = panel
        report = run_g2(wide, "planted_regime", prereg_split=PREREG_SPLIT)
        assert report.first_failure == "g11_market_segments"

    def test_planted_crowded_dies_at_redundancy(self, panel):
        wide, _ = panel
        report = run_g2(wide, "planted_crowded", prereg_split=PREREG_SPLIT,
                        library_cols=["planted_good"])
        assert report.first_failure == "g12_redundancy"

    def test_noise_factors_die_early(self, panel):
        wide, _ = panel
        report = run_g2(wide, "roe_ttm", prereg_split=PREREG_SPLIT)
        assert not report.passed_all
        assert report.first_failure in ("g5_executability", "g6_ic_stability")


class TestGateMechanics:
    def test_fixed_order_enforced(self, panel):
        wide, _ = panel
        report = run_g2(wide, "planted_good", prereg_split=PREREG_SPLIT)
        assert report.executed_order == list(G2_GATE_ORDER)

    def test_short_circuit_stops_at_first_failure(self, panel):
        wide, _ = panel
        report = run_g2(wide, "planted_decay", prereg_split=PREREG_SPLIT)
        # 死在 g8 → g9-g12 不应执行
        assert report.executed_order == list(G2_GATE_ORDER)[:5]

    def test_gate5_filters_for_downstream(self, panel):
        wide, _ = panel
        _, filtered = gate5_executability(wide, "planted_good")
        # 过滤后：无涨跌停/停牌/ST/次新/低流动性
        assert not filtered["limit_up"].any()
        assert not filtered["suspended"].any()
        assert not filtered["is_st"].any()
        assert (filtered["days_since_ipo"] >= 120).all()
        assert (filtered["avg_amount_20d"] >= 2.0e7).all()
        assert len(filtered) < len(wide)


class TestBHFDR:
    def test_single_test_no_penalty(self):
        assert _bh_adjusted_pvalue({"a": 0.01}, "a") == pytest.approx(0.01)

    def test_multiple_tests_inflates_p(self):
        # 100 个独立检验，self p=0.04 → 校正后 > 0.05
        pvals = {f"f{i}": 0.5 for i in range(99)}
        pvals["self"] = 0.04
        assert _bh_adjusted_pvalue(pvals, "self") > 0.05

    def test_extreme_p_survives(self):
        pvals = {f"f{i}": 0.5 for i in range(99)}
        pvals["self"] = 1e-6
        assert _bh_adjusted_pvalue(pvals, "self") <= 0.05


class TestOOSCrossRunAccumulation:
    def test_oos_counter_rejects_fourth_access(self, tmp_path):
        oos = OOSAccessLedger(tmp_path / "oos.json")
        for _ in range(3):
            oos.access("f1")
        from research_core.factor_db.lifecycle import OOSAccessLimitExceeded

        with pytest.raises(OOSAccessLimitExceeded):
            oos.access("f1")
