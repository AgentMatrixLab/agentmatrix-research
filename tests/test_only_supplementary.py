"""TEST-ONLY tests for the batch supplementary evidence layer.

Synthetic validation results only; nothing here says anything about real factors.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research_core.factor_lab.supplementary import (
    SupplementaryError,
    build_supplementary_report,
    industry_neutral_retention,
    p_value_from_t,
    rank_ic_t_stat,
    render_markdown,
)


def _result(factor_id: str, t_stat: float, days: int = 400, horizon: int = 10) -> dict:
    return {
        "factor_id": factor_id,
        "primary_horizon": horizon,
        "rank_ic": {
            str(horizon): {"mean": 0.02, "ic_ir": 0.3, "t_stat": t_stat, "days": days, "yearly": {}}
        },
    }


# ── p-values ────────────────────────────────────────────────────────────

def test_p_value_is_two_sided_and_symmetric() -> None:
    assert p_value_from_t(2.0, 100) == pytest.approx(p_value_from_t(-2.0, 100))


def test_p_value_matches_a_known_quantile() -> None:
    """t = 1.984 with 100 dof is the classical two-sided 5% point."""
    assert p_value_from_t(1.984, 100) == pytest.approx(0.05, abs=2e-3)


def test_larger_t_gives_a_smaller_p() -> None:
    assert p_value_from_t(4.0, 200) < p_value_from_t(2.0, 200)


def test_p_value_is_nan_without_degrees_of_freedom() -> None:
    assert np.isnan(p_value_from_t(2.0, 0))
    assert np.isnan(p_value_from_t(2.0, -3))


def test_p_value_is_nan_for_a_non_finite_t() -> None:
    assert np.isnan(p_value_from_t(float("nan"), 100))
    assert np.isnan(p_value_from_t(float("inf"), 100))


# ── pulling the statistic out of a validation result ────────────────────

def test_rank_ic_t_stat_reads_the_primary_horizon() -> None:
    result = {
        "factor_id": "f",
        "rank_ic": {"5": {"t_stat": 1.0, "days": 10}, "10": {"t_stat": 3.0, "days": 400}},
    }
    assert rank_ic_t_stat(result, primary_horizon=10) == (3.0, 400)


def test_rank_ic_t_stat_falls_back_when_only_one_horizon_exists() -> None:
    result = {"factor_id": "f", "rank_ic": {"5": {"t_stat": 2.0, "days": 50}}}
    assert rank_ic_t_stat(result, primary_horizon=10) == (2.0, 50)


def test_rank_ic_t_stat_refuses_to_guess_an_ambiguous_horizon() -> None:
    result = {
        "factor_id": "f",
        "rank_ic": {"5": {"t_stat": 1.0, "days": 10}, "20": {"t_stat": 3.0, "days": 400}},
    }
    with pytest.raises(SupplementaryError, match="ambiguous"):
        rank_ic_t_stat(result, primary_horizon=10)


def test_rank_ic_t_stat_rejects_a_result_without_rank_ic() -> None:
    with pytest.raises(SupplementaryError, match="no rank_ic"):
        rank_ic_t_stat({"factor_id": "f"})


def test_rank_ic_t_stat_reports_the_factor_id_when_it_fails() -> None:
    with pytest.raises(SupplementaryError, match="MY_FACTOR"):
        rank_ic_t_stat({"factor_id": "MY_FACTOR"})


# ── the report ──────────────────────────────────────────────────────────

def test_report_runs_fdr_and_keeps_input_order() -> None:
    results = [_result("weak", 0.5), _result("strong", 8.0), _result("medium", 3.0)]
    report = build_supplementary_report(results, q=0.05)
    assert [item["factor_id"] for item in report["factors"]] == ["weak", "strong", "medium"]

    by_id = {item["factor_id"]: item for item in report["factors"]}
    assert by_id["strong"]["fdr_accepted"] is True
    assert by_id["weak"]["fdr_accepted"] is False
    assert by_id["strong"]["p_adjusted"] < by_id["weak"]["p_adjusted"]


def test_report_counts_untestable_factors_separately() -> None:
    results = [
        _result("good", 6.0),
        _result("too_short", 6.0, days=1),      # no degrees of freedom
        {"factor_id": "no_ic_table"},            # no rank_ic at all
    ]
    report = build_supplementary_report(results, q=0.05)
    summary = report["summary"]
    assert summary["n_submitted"] == 3
    assert summary["n_tested"] == 1
    assert summary["n_accepted"] == 1

    by_id = {item["factor_id"]: item for item in report["factors"]}
    assert np.isnan(by_id["too_short"]["p_value"])
    assert by_id["too_short"]["fdr_accepted"] is False
    assert by_id["no_ic_table"]["fdr_accepted"] is False


def test_report_includes_the_frozen_gate_t_statistic_verbatim() -> None:
    """The supplementary layer must not recompute what the validator measured."""
    results = [_result("f", 2.5)]
    report = build_supplementary_report(results)
    assert report["factors"][0]["t_stat"] == 2.5


def test_report_attaches_industry_neutral_ic_when_supplied() -> None:
    neutral = {"f": {"retention": 0.72, "neutral": {"mean": 0.015}}}
    report = build_supplementary_report([_result("f", 3.0)], neutral_ic=neutral)
    assert report["factors"][0]["industry_neutral_ic"]["retention"] == 0.72


def test_report_tolerates_a_missing_neutral_entry() -> None:
    report = build_supplementary_report([_result("f", 3.0)], neutral_ic={"other": None})
    assert report["factors"][0]["industry_neutral_ic"] is None


def test_report_handles_an_empty_batch() -> None:
    report = build_supplementary_report([])
    assert report["summary"]["n_submitted"] == 0
    assert report["factors"] == []


def test_report_quantifies_the_cost_of_the_correction() -> None:
    """The gap between uncorrected and corrected significance must be visible."""
    # t = 1.72-1.90 clears the frozen |t| >= 1.65 gate but has two-sided p > 0.05.
    results = [_result(f"marginal{i}", 1.72 + i * 0.05) for i in range(5)]
    report = build_supplementary_report(results, q=0.05)
    marginal = report["marginal_effect"]
    assert marginal["passed_uncorrected"] == 0
    assert marginal["passed_fdr"] == 0
    assert marginal["lost_to_correction"] == 0
    assert report["p_value_convention"].startswith("two-sided")


def test_report_lists_factors_lost_to_multiple_testing() -> None:
    """A batch where some factors clear uncorrected significance but not FDR."""
    results = [_result(f"f{i}", 1.70 + i * 0.002) for i in range(200)]
    report = build_supplementary_report(results, q=0.05)
    marginal = report["marginal_effect"]
    assert marginal["passed_uncorrected"] > marginal["passed_fdr"]
    assert marginal["lost_to_correction"] == (
        marginal["passed_uncorrected"] - marginal["passed_fdr"]
    )
    assert len(marginal["lost_factor_ids"]) == marginal["lost_to_correction"]


def test_fdr_is_not_reported_as_stronger_than_uncorrected() -> None:
    """The structural guarantee, at report level."""
    results = [_result(f"f{i}", 1.70 + i * 0.01) for i in range(60)]
    report = build_supplementary_report(results, q=0.05)
    by_id = {item["factor_id"]: item for item in report["factors"]}
    uncorrected = {i for i, item in by_id.items() if item["p_value"] < 0.05}
    corrected = {i for i, item in by_id.items() if item["fdr_accepted"]}
    assert corrected <= uncorrected


# ── industry-neutral retention against a real panel ─────────────────────

def _industry_panel(seed: int = 4) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for date_index in range(30):
        stamp = pd.Timestamp("2023-01-02") + pd.Timedelta(days=date_index)
        effects = {"A": rng.normal(0, 0.05), "B": rng.normal(0, 0.05)}
        for name in ("A", "B"):
            for stock in range(40):
                rows.append(
                    {
                        "date": stamp,
                        "code": f"{name}_{stock}",
                        "industry": name,
                        "forward_return": effects[name] + rng.normal(0, 0.01),
                    }
                )
    return pd.DataFrame(rows)


def test_industry_neutral_retention_returns_none_without_an_industry_column() -> None:
    panel = pd.DataFrame({"date": [1], "forward_return": [0.1], "factor": [1.0]})
    assert (
        industry_neutral_retention(
            panel, factor_values=None, factor_col="factor", return_col="forward_return"
        )
        is None
    )


def test_industry_neutral_retention_returns_none_without_factor_values() -> None:
    panel = _industry_panel()
    assert (
        industry_neutral_retention(
            panel, factor_values=None, factor_col="factor", return_col="forward_return"
        )
        is None
    )


def test_industry_neutral_retention_uses_supplied_factor_values() -> None:
    panel = _industry_panel()
    rng = np.random.default_rng(8)
    values = pd.Series(rng.normal(0, 1, len(panel)), index=panel.index)
    result = industry_neutral_retention(
        panel,
        factor_values=values,
        factor_col="factor",
        return_col="forward_return",
    )
    assert result is not None
    assert "retention" in result
    assert result["industries"] == 2


# ── markdown ────────────────────────────────────────────────────────────

def test_markdown_states_the_additive_contract() -> None:
    report = build_supplementary_report([_result("f", 3.0)], q=0.05)
    text = render_markdown(report)
    assert "追加证据层" in text
    assert "不修改任何已冻结门槛" in text


def test_markdown_explains_the_one_sided_versus_two_sided_gap() -> None:
    """The gate screens one-sided; FDR is applied two-sided. Say so."""
    report = build_supplementary_report([_result("f", 3.0)], q=0.05)
    text = render_markdown(report)
    assert "单侧" in text and "双侧" in text
    assert "校正的代价" in text


def test_markdown_lists_accepted_factors_first() -> None:
    results = [_result("weak", 0.5), _result("strong", 9.0)]
    text = render_markdown(build_supplementary_report(results))
    assert text.index("strong") < text.index("weak")


def test_markdown_truncates_a_long_batch() -> None:
    results = [_result(f"f{i}", 1.0 + i * 0.1) for i in range(100)]
    text = render_markdown(build_supplementary_report(results), limit=10)
    assert "此处只列前 10 个" in text
