"""TEST-ONLY tests for the additive robustness dimensions.

The panels here are synthetic and exist to pin the *mathematics*. They are not
market data and say nothing about any factor's predictive power.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research_core.factor_lab.robustness import (
    benjamini_hochberg,
    demean_within_groups,
    excess_forward_returns,
    forward_returns,
    ic_series,
    industry_neutral_ic,
    summarize_ic,
)


# ── Benjamini-Hochberg ──────────────────────────────────────────────────

def test_bh_accepts_nothing_when_no_p_value_clears_the_bar() -> None:
    result = benjamini_hochberg([0.4, 0.6, 0.9], q=0.05)
    assert result.n_accepted == 0
    assert result.n_rejected == 3


def test_bh_accepts_everything_when_all_are_tiny() -> None:
    result = benjamini_hochberg([1e-6, 1e-5, 1e-4], q=0.05)
    assert result.n_accepted == 3


def test_bh_known_worked_example() -> None:
    """Hand-computed textbook case.

    p = [0.001, 0.008, 0.039, 0.041, 0.042, 0.06, 0.074, 0.205, 0.212, 0.216,
         0.222, 0.251, 0.269, 0.275, 0.34]
    at q = 0.05 the largest k with p_(k) <= k/n * q is k = 4
    (0.041 <= 4/15*0.05 = 0.01333 is false) -> k = 3 (0.039 <= 0.01 false)
    -> k = 2 (0.008 <= 0.006667 false) -> k = 1 (0.001 <= 0.003333 true).
    """
    p = [0.001, 0.008, 0.039, 0.041, 0.042, 0.06, 0.074, 0.205, 0.212, 0.216,
         0.222, 0.251, 0.269, 0.275, 0.34]
    result = benjamini_hochberg(p, q=0.05)
    assert result.n_tested == 15
    assert result.n_accepted == 1
    assert result.accepted[0] is True
    assert not any(result.accepted[1:])


def test_bh_adjusted_p_values_are_monotone_in_rank() -> None:
    p = [0.001, 0.02, 0.04, 0.5, 0.9]
    result = benjamini_hochberg(p, q=0.1)
    ordered = [result.adjusted[i] for i in np.argsort(p)]
    assert ordered == sorted(ordered)
    assert all(0.0 <= value <= 1.0 for value in result.adjusted)


def test_bh_adjusted_is_never_smaller_than_raw() -> None:
    p = [0.001, 0.01, 0.02, 0.03, 0.2]
    result = benjamini_hochberg(p, q=0.05)
    for raw, adjusted in zip(p, result.adjusted):
        assert adjusted >= raw - 1e-12


def test_bh_never_accepts_a_nan_p_value() -> None:
    """A factor we could not test must not count as a discovery."""
    result = benjamini_hochberg([0.001, float("nan"), 0.002], q=0.05)
    assert result.n_accepted == 2
    assert result.accepted[1] is False
    assert result.n_submitted == 3
    assert result.n_tested == 2


def test_bh_untestable_factors_do_not_dilute_the_correction() -> None:
    """Padding the batch with untestable factors must not weaken the threshold."""
    clean = benjamini_hochberg([0.01, 0.02, 0.03], q=0.05)
    padded = benjamini_hochberg([0.01, 0.02, 0.03, float("nan"), float("nan")], q=0.05)
    assert padded.n_accepted == clean.n_accepted
    assert padded.adjusted[:3] == pytest.approx(clean.adjusted)


def test_bh_all_untestable_accepts_nothing() -> None:
    result = benjamini_hochberg([float("nan"), float("nan")], q=0.05)
    assert result.n_tested == 0
    assert result.n_accepted == 0
    assert result.accepted == (False, False)


def test_bh_preserves_input_order() -> None:
    """The mask must line up with the caller's factor list, not the sort order."""
    p = [0.9, 0.001, 0.5]
    result = benjamini_hochberg(p, q=0.05)
    assert result.accepted[1] is True
    assert result.accepted[0] is False
    assert result.accepted[2] is False


def test_bh_is_stricter_than_uncorrected_significance() -> None:
    """The point of the correction: 50 marginal p-values must not all survive."""
    rng = np.random.default_rng(7)
    p = rng.uniform(0.001, 0.05, 50).tolist()
    uncorrected = sum(1 for value in p if value < 0.05)
    corrected = benjamini_hochberg(p, q=0.05).n_accepted
    assert uncorrected == 50
    assert corrected < uncorrected


def test_bh_handles_the_empty_batch() -> None:
    result = benjamini_hochberg([], q=0.05)
    assert result.n_tested == 0
    assert result.n_accepted == 0
    assert result.accepted == ()


def test_bh_rejects_an_invalid_q() -> None:
    for bad in (0.0, 1.0, -0.1, 1.5):
        with pytest.raises(ValueError, match="q must lie"):
            benjamini_hochberg([0.01], q=bad)


def test_bh_rejects_out_of_range_p_values() -> None:
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        benjamini_hochberg([0.5, 1.4], q=0.05)


# ── forward returns ─────────────────────────────────────────────────────

def test_forward_returns_respect_code_boundaries() -> None:
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(
                ["2023-01-02", "2023-01-03", "2023-01-04"] * 2
            ),
            "code": ["A"] * 3 + ["B"] * 3,
            "close": [10.0, 11.0, 12.0, 20.0, 18.0, 22.0],
        }
    )
    result = forward_returns(frame.sort_values(["code", "date"]).reset_index(drop=True), horizon=1)
    ordered = frame.sort_values(["code", "date"]).reset_index(drop=True)
    got = result.reindex(ordered.index)
    assert got.iloc[0] == pytest.approx(0.1)          # A: 11/10 - 1
    assert got.iloc[2] != got.iloc[2]                  # A's last bar is NaN
    assert np.isnan(got.iloc[2])
    assert got.iloc[3] == pytest.approx(18.0 / 20.0 - 1.0)  # B never crosses into A


def test_excess_forward_returns_subtract_the_benchmark() -> None:
    returns = pd.Series([0.02, 0.03, -0.01])
    dates = pd.Series(pd.to_datetime(["2023-01-03", "2023-01-04", "2023-01-05"]))
    benchmark = pd.Series(
        [0.01, 0.01, 0.00],
        index=pd.to_datetime(["2023-01-03", "2023-01-04", "2023-01-05"]),
    )
    result = excess_forward_returns(returns, dates, benchmark)
    assert list(np.round(np.asarray(result), 10)) == [0.01, 0.02, -0.01]


# ── group demeaning ─────────────────────────────────────────────────────

def test_demean_within_groups_removes_the_group_effect() -> None:
    values = pd.Series([1.0, 2.0, 10.0, 12.0])
    dates = pd.Series(["d1"] * 4)
    groups = pd.Series(["A", "A", "B", "B"])
    result = demean_within_groups(values, dates, groups)
    assert result.tolist() == pytest.approx([-0.5, 0.5, -1.0, 1.0])


def test_demean_within_groups_is_per_date() -> None:
    """Same group label on different dates must not be pooled."""
    values = pd.Series([1.0, 3.0, 100.0, 102.0])
    dates = pd.Series(["d1", "d1", "d2", "d2"])
    groups = pd.Series(["A", "A", "A", "A"])
    result = demean_within_groups(values, dates, groups)
    assert result.tolist() == pytest.approx([-1.0, 1.0, -1.0, 1.0])


# ── industry neutralisation ─────────────────────────────────────────────

def _panel(
    n_industries: int = 4,
    n_per_industry: int = 60,
    n_dates: int = 40,
    seed: int = 11,
    industry_sigma: float = 0.05,
) -> pd.DataFrame:
    """Long panel carrying a per-(date, industry) return effect.

    The effect is redrawn every date, so a factor that merely *names* an industry
    has no systematic rank relationship with returns -- it has to carry the
    realised effect to score a high raw IC.
    """
    rng = np.random.default_rng(seed)
    rows = []
    industries = [f"IND{i}" for i in range(n_industries)]
    for date_index in range(n_dates):
        stamp = pd.Timestamp("2023-01-02") + pd.Timedelta(days=date_index)
        effects = {name: rng.normal(0, industry_sigma) for name in industries}
        for name in industries:
            for stock in range(n_per_industry):
                rows.append(
                    {
                        "date": stamp,
                        "code": f"{name}_{stock}",
                        "industry": name,
                        "industry_effect": effects[name],
                    }
                )
    return pd.DataFrame(rows)


def test_industry_neutral_ic_kills_a_pure_industry_bet() -> None:
    """A factor that only reproduces the industry return must not survive.

    This is the exact failure the frozen style gate cannot see: the factor has
    strong raw IC because it tracks the industry effect, and zero IC once
    industries are removed.
    """
    rng = np.random.default_rng(3)
    frame = _panel()
    # Factor carries the industry's realised effect plus a little noise.
    frame["factor"] = frame["industry_effect"] + rng.normal(0, 0.002, len(frame))
    # Returns are mostly the same industry effect, with wider idiosyncratic noise
    # that the factor knows nothing about.
    frame["return"] = frame["industry_effect"] + rng.normal(0, 0.010, len(frame))

    result = industry_neutral_ic(frame, factor_col="factor", return_col="return")
    assert abs(result["raw"]["mean"]) > 0.5, "raw IC should be dominated by the industry effect"
    assert abs(result["neutral"]["mean"]) < 0.1, "neutral IC should collapse"
    assert abs(result["retention"]) < 0.2


def test_a_factor_that_only_names_the_industry_has_no_ic_at_all() -> None:
    """Labelling an industry is not a signal: the effect is redrawn each date."""
    rng = np.random.default_rng(21)
    frame = _panel()
    frame["factor"] = frame["industry"].astype("category").cat.codes.astype(float)
    frame["return"] = frame["industry_effect"] + rng.normal(0, 0.010, len(frame))
    result = industry_neutral_ic(frame, factor_col="factor", return_col="return")
    assert abs(result["raw"]["mean"]) < 0.1


def test_industry_neutral_ic_preserves_a_genuine_within_industry_signal() -> None:
    """A real signal inside industries must survive neutralisation."""
    rng = np.random.default_rng(5)
    frame = _panel()
    signal = rng.normal(0, 1, len(frame))
    frame["factor"] = signal
    frame["return"] = 0.02 * signal + frame["industry_effect"] + rng.normal(0, 1e-4, len(frame))

    result = industry_neutral_ic(frame, factor_col="factor", return_col="return")
    assert result["neutral"]["mean"] > 0.5
    assert result["neutral"]["t_stat"] > 10


def test_industry_neutral_ic_reports_a_retention_ratio() -> None:
    rng = np.random.default_rng(9)
    frame = _panel()
    frame["factor"] = rng.normal(0, 1, len(frame))
    frame["return"] = 0.01 * frame["factor"] + frame["industry_effect"]
    result = industry_neutral_ic(frame, factor_col="factor", return_col="return")
    assert np.isfinite(result["retention"])
    assert result["industries"] == 4


def test_industry_neutral_ic_stricter_mode_also_removes_return_side_exposure() -> None:
    rng = np.random.default_rng(13)
    frame = _panel()
    frame["factor"] = rng.normal(0, 1, len(frame)) + frame["industry_effect"] * 100
    frame["return"] = frame["industry_effect"] + 0.01 * rng.normal(0, 1, len(frame))

    lenient = industry_neutral_ic(
        frame, factor_col="factor", return_col="return", neutralize_returns=False
    )
    strict = industry_neutral_ic(
        frame, factor_col="factor", return_col="return", neutralize_returns=True
    )
    assert strict["neutralize_returns"] is True
    assert abs(strict["neutral"]["mean"]) <= abs(lenient["neutral"]["mean"]) + 1e-9


def test_industry_neutral_ic_names_the_missing_column() -> None:
    frame = pd.DataFrame({"date": [], "close": []})
    with pytest.raises(KeyError, match="industry"):
        industry_neutral_ic(frame, factor_col="factor", return_col="return")


# ── IC plumbing ─────────────────────────────────────────────────────────

def test_ic_series_skips_cross_sections_below_the_minimum() -> None:
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(["2023-01-02"] * 5 + ["2023-01-03"] * 30),
            "factor": list(range(5)) + list(range(30)),
            "return": list(range(5)) + list(range(30)),
        }
    )
    series = ic_series(frame["factor"], frame["return"], frame["date"], minimum_cross_section=20)
    assert len(series) == 1


def test_ic_series_skips_a_constant_cross_section() -> None:
    """A constant factor has no rank correlation; it must not be reported as 0."""
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(["2023-01-02"] * 30),
            "factor": [1.0] * 30,
            "return": list(range(30)),
        }
    )
    assert ic_series(frame["factor"], frame["return"], frame["date"]).empty


def test_summarize_ic_is_nan_safe_on_an_empty_series() -> None:
    result = summarize_ic(pd.Series(dtype=float))
    assert result["days"] == 0
    assert np.isnan(result["mean"])


def test_summarize_ic_matches_a_hand_computation() -> None:
    series = pd.Series([0.1, 0.2, 0.3, 0.4])
    result = summarize_ic(series, ddof=1)
    assert result["mean"] == pytest.approx(0.25)
    assert result["ic_ir"] == pytest.approx(0.25 / series.std(ddof=1))
    assert result["days"] == 4
