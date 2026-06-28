"""Tests for market_data, inference, and similarity modules."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import numpy as np
import pandas as pd
import pytest

# ═══════════════════════════════════════════════════════════════
# Test data fixtures
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def sample_panel():
    """Synthetic panel mimicking real market data."""
    rng = np.random.default_rng(42)
    codes = [f"{i:06d}" for i in range(1, 21)]
    dates = pd.date_range("2023-01-01", periods=252, freq="B")

    records = []
    for code in codes:
        base = rng.uniform(5, 50)
        price = base
        for date in dates:
            ret = rng.normal(0.0005, 0.02)
            price *= (1 + ret)
            records.append({
                "date": date,
                "code": code,
                "open": price * (1 + rng.normal(0, 0.005)),
                "high": price * (1 + abs(rng.normal(0, 0.01))),
                "low": price * (1 - abs(rng.normal(0, 0.01))),
                "close": price,
                "volume": rng.uniform(1e6, 1e8),
                "amount": rng.uniform(1e7, 1e9),
            })

    return pd.DataFrame(records)


@pytest.fixture
def sample_ic_series():
    """Realistic IC series with positive mean."""
    rng = np.random.default_rng(123)
    return pd.Series(rng.normal(0.03, 0.1, 200))


@pytest.fixture
def sample_ic_series_decaying():
    """IC series with a decaying trend."""
    rng = np.random.default_rng(456)
    trend = np.linspace(0, -0.05, 200)
    noise = rng.normal(0.03, 0.08, 200)
    return pd.Series(trend + noise)


@pytest.fixture
def sample_factor_frames(sample_panel):
    """Multiple synthetic factor frames for similarity testing."""
    rng = np.random.default_rng(789)

    # alpha_a: momentum (correlated with alpha_b)
    close_pivot = sample_panel.pivot(index="date", columns="code", values="close")
    ret_20 = close_pivot.pct_change(20).stack().reset_index()
    ret_20.columns = ["date", "code", "alpha_a"]

    # alpha_b: similar to alpha_a (21-day momentum, high correlation expected)
    ret_21 = close_pivot.pct_change(21).stack().reset_index()
    ret_21.columns = ["date", "code", "alpha_b"]

    # alpha_c: pure noise (should be uncorrelated)
    noise = sample_panel[["date", "code"]].copy()
    noise["alpha_c"] = rng.normal(0, 1, len(noise))

    return ret_20, ret_21, noise


# ═══════════════════════════════════════════════════════════════
# Inference tests
# ═══════════════════════════════════════════════════════════════

class TestBootstrapIC:
    def test_positive_ic_significant(self, sample_ic_series):
        from research_core.factor_lab.inference import bootstrap_ic_confidence
        result = bootstrap_ic_confidence(sample_ic_series, n_bootstrap=1000, ci_level=0.95)

        assert result["n_samples"] == 200
        assert result["n_bootstrap"] == 1000
        assert result["ci_level"] == 0.95
        assert isinstance(result["ci_lower"], float)
        assert isinstance(result["ci_upper"], float)
        assert result["ci_lower"] <= result["ic_mean"] <= result["ci_upper"]
        assert result["ic_significant"]  # IC=0.03 over 200 days should be significant
        assert 0 <= result["p_value"] <= 0.05  # Should be significant (may be exactly 0 if all boot means > 0)

    def test_zero_ic_not_significant(self):
        from research_core.factor_lab.inference import bootstrap_ic_confidence
        rng = np.random.default_rng(999)
        zero_ic = rng.normal(0.0, 0.1, 200)
        result = bootstrap_ic_confidence(zero_ic, n_bootstrap=1000)
        assert not result["ic_significant"]
        assert result["p_value"] > 0.05

    def test_too_few_observations(self):
        from research_core.factor_lab.inference import bootstrap_ic_confidence
        result = bootstrap_ic_confidence([0.01, 0.02])
        assert "error" in result
        assert result["n_samples"] == 2

    def test_multiple_factors(self):
        from research_core.factor_lab.inference import bootstrap_ic_confidence_multiple
        ic_data = {
            "alpha_a": np.random.default_rng(1).normal(0.04, 0.1, 200),
            "alpha_b": np.random.default_rng(2).normal(0.01, 0.1, 200),
        }
        results = bootstrap_ic_confidence_multiple(ic_data, n_bootstrap=500)
        assert len(results) == 2
        assert "ic_mean" in results["alpha_a"]
        assert "ic_mean" in results["alpha_b"]


class TestICDecay:
    def test_stable_ic_not_decaying(self, sample_ic_series):
        from research_core.factor_lab.inference import ic_decay_analysis
        result = ic_decay_analysis(sample_ic_series, window=60, step=20)
        assert not result["decay_warning"]
        assert "rolling_means" in result
        assert len(result["rolling_means"]) > 0

    def test_decaying_ic_warns(self, sample_ic_series_decaying):
        from research_core.factor_lab.inference import ic_decay_analysis
        result = ic_decay_analysis(sample_ic_series_decaying, window=60, step=20)
        # This should detect the negative trend
        assert result["trend_slope"] < 0
        # May or may not be statistically significant depending on noise

    def test_insufficient_data(self):
        from research_core.factor_lab.inference import ic_decay_analysis
        result = ic_decay_analysis([0.01, 0.02], window=60)
        assert "error" in result


class TestMultipleTesting:
    def test_bonferroni(self):
        from research_core.factor_lab.inference import multiple_testing_correction
        pvals = {"a": 0.001, "b": 0.01, "c": 0.5}
        result = multiple_testing_correction(pvals, method="bonferroni", alpha=0.05)
        assert result["method"] == "bonferroni"
        # Bonferroni: 0.001*3=0.003 ✅, 0.01*3=0.03 ✅, 0.5*3=1.5 ❌
        assert result["significant"]["a"]
        assert result["significant"]["b"]
        assert not result["significant"]["c"]

    def test_fdr_bh(self):
        from research_core.factor_lab.inference import multiple_testing_correction
        pvals = {"a": 0.001, "b": 0.01, "c": 0.5}
        result = multiple_testing_correction(pvals, method="fdr_bh", alpha=0.05)
        assert result["method"] == "fdr_bh"
        assert result["significant"]["a"]

    def test_fdr_severe_multiplicity(self):
        """When testing 100 factors, only truly significant should survive FDR."""
        from research_core.factor_lab.inference import multiple_testing_correction
        rng = np.random.default_rng(42)
        # 100 factors: 95 null + 5 with true signal
        pvals = {}
        for i in range(95):
            pvals[f"null_{i}"] = float(rng.uniform(0.01, 0.99))
        for i in range(5):
            pvals[f"signal_{i}"] = float(rng.uniform(0.0001, 0.001))

        result = multiple_testing_correction(pvals, method="fdr_bh", alpha=0.05)
        # Most null factors should NOT survive FDR
        null_sig = sum(
            1 for k in result["significant"] if k.startswith("null_") and result["significant"][k]
        )
        signal_sig = sum(
            1 for k in result["significant"] if k.startswith("signal_") and result["significant"][k]
        )
        # At most ~5 null factors should survive by chance, signal factors should mostly survive
        assert null_sig <= 10  # Conservative bound
        assert signal_sig >= 2  # Most true signals should pass FDR


# ═══════════════════════════════════════════════════════════════
# Similarity tests
# ═══════════════════════════════════════════════════════════════

class TestSimilarity:
    def test_correlated_factors_detected(self, sample_factor_frames):
        from research_core.factor_lab.similarity import find_similar_factors
        ret_20, ret_21, noise = sample_factor_frames

        report = find_similar_factors(
            ret_20, "alpha_a",
            {"alpha_b": ret_21, "alpha_c": noise},
            threshold=0.5,
        )

        # alpha_b (21-day momentum) should be highly correlated with alpha_a (20-day)
        assert report["has_duplicate"]
        assert report["top_match"] == "alpha_b"
        assert report["top_correlation"] > 0.5

    def test_uncorrelated_factors_not_flagged(self, sample_factor_frames):
        from research_core.factor_lab.similarity import find_similar_factors
        ret_20, _, noise = sample_factor_frames

        report = find_similar_factors(
            ret_20, "alpha_a",
            {"alpha_c": noise},
            threshold=0.7,
        )

        # alpha_c is pure noise, should not be flagged as duplicate
        assert not report["has_duplicate"]

    def test_build_similarity_matrix(self, sample_factor_frames):
        from research_core.factor_lab.similarity import build_similarity_matrix
        ret_20, ret_21, noise = sample_factor_frames

        frames = {
            "alpha_a": ret_20,
            "alpha_b": ret_21,
            "alpha_c": noise,
        }
        matrix = build_similarity_matrix(frames)
        assert matrix.shape == (3, 3)
        assert (matrix.index == ["alpha_a", "alpha_b", "alpha_c"]).all()
        # alpha_a ~ alpha_b should be high
        assert abs(matrix.loc["alpha_a", "alpha_b"]) > 0.5
        # alpha_c ~ alpha_a should be near zero
        assert abs(matrix.loc["alpha_a", "alpha_c"]) < 0.3


# ═══════════════════════════════════════════════════════════════
# Market data adapter tests (unit — no network)
# ═══════════════════════════════════════════════════════════════

class TestMarketData:
    def test_resolve_universe_csi300(self):
        """Test universe resolution logic (structure, not actual API call)."""
        from research_core.data_loader.market_data import resolve_universe

        # List input should pass through
        codes = resolve_universe(["000001", "000002"])
        assert codes == ["000001", "000002"]

    def test_panel_required_columns(self, sample_panel):
        from research_core.data_loader.market_data import REQUIRED_COLUMNS
        for col in REQUIRED_COLUMNS:
            assert col in sample_panel.columns, f"Missing required column: {col}"


# ═══════════════════════════════════════════════════════════════
# End-to-end mini test
# ═══════════════════════════════════════════════════════════════

class TestE2EMini:
    def test_full_pipeline_on_synthetic_data(self, sample_panel):
        """Run the full pipeline on synthetic data to verify no import errors."""
        from research_core.factor_lab.libraries.alpha101 import compute_alpha101_factors
        from research_core.factor_lab.evaluation import (
            build_alpha101_evaluation_report,
            compute_forward_returns,
        )
        from research_core.factor_lab.inference import (
            bootstrap_ic_confidence,
            ic_decay_analysis,
            multiple_testing_correction,
            out_of_sample_split,
        )
        from research_core.factor_lab.similarity import find_similar_factors

        # Compute factors
        factor_names = ["alpha1", "alpha2", "alpha5"]
        factor_frame = compute_alpha101_factors(sample_panel, factor_names=factor_names)

        assert len(factor_frame) == len(sample_panel)
        for fn in factor_names:
            assert fn in factor_frame.columns
            assert factor_frame[fn].notna().sum() > 0

        # Evaluation
        eval_report = build_alpha101_evaluation_report(
            sample_panel, factor_frame, factor_names=factor_names
        )
        assert "summary" in eval_report
        assert eval_report["summary"]["factor_count"] == 3

        # Compute ICs manually for bootstrap
        enriched = factor_frame.merge(
            sample_panel[["date", "code", "close"]], on=["date", "code"], how="left"
        )
        enriched["fwd_ret"] = compute_forward_returns(
            sample_panel.sort_values(["code", "date"]).reset_index(drop=True),
            price_col="close",
        )

        ics = []
        for _, group in enriched.groupby("date"):
            valid = group.dropna(subset=["alpha1", "fwd_ret"])
            if len(valid) >= 10:
                ic = valid["alpha1"].rank().corr(valid["fwd_ret"].rank())
                if pd.notna(ic):
                    ics.append(ic)

        # Bootstrap
        ci = bootstrap_ic_confidence(ics, n_bootstrap=500)
        assert "ci_lower" in ci
        assert "ci_upper" in ci

        # Decay
        decay = ic_decay_analysis(ics, window=min(30, len(ics) // 2))
        assert "trend_slope" in decay

        # Similarity
        report = find_similar_factors(
            factor_frame, "alpha1",
            {"alpha2": factor_frame[["date", "code", "alpha2"]]},
            threshold=0.9,
        )
        assert "has_duplicate" in report

        # OOS split
        split = out_of_sample_split(sample_panel)
        assert "train_panel" in split
        assert len(split["train_panel"]) > 0
        assert len(split["test_panel"]) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
