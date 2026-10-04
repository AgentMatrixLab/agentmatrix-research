"""TEST-ONLY tests for the scoring card and correlation clustering.

Synthetic validation results only; these pin the card's arithmetic and its two
structural guarantees, and say nothing about any real factor.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from research_core.factor_lab.scoring import (
    SCORE_CARD,
    TOTAL_WEIGHT,
    ScoringError,
    assign_tier,
    cluster_factors,
    score_batch,
    score_factor,
    select_representatives,
)


def _result(
    factor_id: str = "f",
    *,
    ic: float = 0.03,
    ic_ir: float = 0.6,
    t_stat: float = 3.0,
    train_ic: float | None = None,
    gross: float = 0.15,
    net: float = 0.09,
    turnover: float = 0.4,
    style_retention: float = 0.8,
    yearly: dict | None = None,
    failed: list[str] | None = None,
) -> dict:
    return {
        "factor_id": factor_id,
        "primary_horizon": 10,
        "rank_ic": {
            "10": {
                "mean": ic,
                "ic_ir": ic_ir,
                "t_stat": t_stat,
                "days": 420,
                "yearly": yearly
                if yearly is not None
                else {str(2023 + i): {"mean": ic, "days": 140} for i in range(3)},
            }
        },
        "training": {"primary_rank_ic_mean": ic if train_ic is None else train_ic},
        "style": {"retention": style_retention},
        "portfolio": {
            "gross_annualized": gross,
            "net_annualized": net,
            "mean_turnover": turnover,
            "round_trip_cost": 0.003,
        },
        "failed_gates": failed or [],
        "result_hash": "deadbeef",
    }


# ── structural guarantee 1: cannot override a gate ──────────────────────

def test_scorer_refuses_a_factor_that_failed_a_frozen_gate() -> None:
    with pytest.raises(ScoringError, match="failed frozen gates"):
        score_factor(_result(failed=["cost_adjusted_return"]))


def test_scorer_names_the_failing_gate() -> None:
    with pytest.raises(ScoringError, match="rank_ic"):
        score_factor(_result(failed=["rank_ic"]))


def test_unvalidated_scoring_is_possible_but_stamped_diagnostic() -> None:
    payload = score_factor(_result(failed=["rank_ic"]), allow_unvalidated=True)
    assert payload["diagnostic_only"] is True
    assert payload["failed_gates"] == ["rank_ic"]


def test_a_clean_factor_is_not_marked_diagnostic() -> None:
    assert score_factor(_result())["diagnostic_only"] is False


def test_batch_skips_failures_instead_of_rescuing_them() -> None:
    batch = score_batch([_result("ok"), _result("bad", failed=["rank_ic"])])
    assert batch["n_scored"] == 1
    assert batch["n_skipped"] == 1
    assert batch["skipped"][0]["factor_id"] == "bad"


# ── structural guarantee 2: no recomputation ────────────────────────────

def test_score_reads_the_validators_t_statistic_verbatim() -> None:
    payload = score_factor(_result(t_stat=2.75))
    entry = next(d for d in payload["dimensions"] if d["name"] == "ic_t_stat")
    assert entry["raw"] == 2.75


def test_score_carries_the_source_result_hash() -> None:
    assert score_factor(_result())["source_result_hash"] == "deadbeef"


# ── structural guarantee 3: every point traces to a number ─────────────

def test_every_dimension_reports_raw_score_weight_and_points() -> None:
    payload = score_factor(_result())
    assert payload["dimensions"], "at least one dimension should be available"
    for entry in payload["dimensions"]:
        assert set(entry) == {"name", "label", "weight", "raw", "score", "points"}
        assert 0.0 <= entry["score"] <= 1.0
        assert entry["points"] == pytest.approx(entry["score"] * entry["weight"])


def test_points_sum_to_the_composite_when_all_weights_are_available() -> None:
    payload = score_factor(
        _result(), capacity=1e9, library_correlation=0.1
    )
    assert payload["weight_available"] == TOTAL_WEIGHT
    total_points = sum(entry["points"] for entry in payload["dimensions"])
    assert payload["composite"] == pytest.approx(total_points)


# ── missing dimensions ──────────────────────────────────────────────────

def test_missing_dimensions_are_renormalised_not_zeroed() -> None:
    """A gap in the pipeline must not read as a weak factor."""
    without_optional = score_factor(_result())
    # capacity (5) and library_increment (2) both need inputs the validator
    # result does not carry, so 7 points of weight are unavailable.
    assert set(without_optional["missing_dimensions"]) == {"capacity", "library_increment"}
    assert without_optional["weight_available"] == TOTAL_WEIGHT - 7
    assert without_optional["weight_coverage"] == pytest.approx(93 / 100)


def test_supplying_an_optional_input_recovers_its_weight() -> None:
    with_capacity = score_factor(_result(), capacity=1e9)
    assert "capacity" not in with_capacity["missing_dimensions"]
    assert with_capacity["weight_available"] == TOTAL_WEIGHT - 2


def test_a_factor_with_only_weak_inputs_still_scores_low() -> None:
    """Renormalisation must not turn a bad factor into a good one."""
    weak = score_factor(
        _result(ic=0.010, ic_ir=0.05, t_stat=1.66, train_ic=0.05, gross=0.02, net=0.019,
                turnover=1.0, style_retention=0.5)
    )
    assert weak["composite"] < 25


def test_a_strong_factor_scores_high() -> None:
    strong = score_factor(
        _result(ic=0.08, ic_ir=1.4, t_stat=6.0, train_ic=0.085, gross=0.30, net=0.25,
                turnover=0.15, style_retention=0.98),
        capacity=1e10, library_correlation=0.0,
    )
    assert strong["composite"] > 90
    assert strong["tier"] in ("S", "A")


def test_scoring_with_no_usable_dimension_gives_nan_not_a_number() -> None:
    payload = score_factor({"factor_id": "empty", "failed_gates": []})
    assert math.isnan(payload["composite"])
    assert payload["tier"] == "C"


# ── individual dimensions ───────────────────────────────────────────────

def test_oos_retention_of_a_sign_flip_is_zero() -> None:
    payload = score_factor(_result(ic=-0.03, train_ic=0.03))
    entry = next(d for d in payload["dimensions"] if d["name"] == "oos_retention")
    assert entry["score"] == 0.0
    assert entry["raw"] < 0


def test_oos_retention_is_one_at_or_above_parity() -> None:
    payload = score_factor(_result(ic=0.03, train_ic=0.03))
    entry = next(d for d in payload["dimensions"] if d["name"] == "oos_retention")
    assert entry["score"] == 1.0


def test_cost_resilience_is_gross_over_the_cost_drag() -> None:
    payload = score_factor(_result(gross=0.15, net=0.09))
    entry = next(d for d in payload["dimensions"] if d["name"] == "cost_resilience")
    assert entry["raw"] == pytest.approx(0.15 / 0.06)


def test_cost_resilience_is_unavailable_without_a_cost_drag() -> None:
    payload = score_factor(_result(gross=0.10, net=0.10))
    assert "cost_resilience" in payload["missing_dimensions"]


def test_turnover_is_annualised_with_the_rebalance_stride() -> None:
    """0.4 per rebalance at a 10-day stride is ~10x annualised round-trip turnover."""
    payload = score_factor(_result(turnover=0.4), periods_per_year=25.2)
    entry = next(d for d in payload["dimensions"] if d["name"] == "turnover")
    assert entry["raw"] == pytest.approx(0.4 * 25.2)
    # 2x scores full marks and 12x scores nothing, so 10x interpolates low.
    assert 0.0 < entry["score"] < 0.25


def test_turnover_between_the_anchors_interpolates_linearly() -> None:
    payload = score_factor(_result(turnover=7.0 / 25.2), periods_per_year=25.2)
    entry = next(d for d in payload["dimensions"] if d["name"] == "turnover")
    assert entry["raw"] == pytest.approx(7.0)
    assert entry["score"] == pytest.approx(0.5)


def test_low_turnover_scores_full_marks() -> None:
    payload = score_factor(_result(turnover=0.05))
    entry = next(d for d in payload["dimensions"] if d["name"] == "turnover")
    assert entry["score"] == 1.0


def test_market_segments_counts_years_agreeing_with_the_overall_sign() -> None:
    yearly = {"2023": {"mean": 0.03}, "2024": {"mean": 0.02}, "2025": {"mean": -0.01}}
    payload = score_factor(_result(ic=0.02, yearly=yearly))
    entry = next(d for d in payload["dimensions"] if d["name"] == "market_segments")
    assert entry["raw"] == pytest.approx(2 / 3)


def test_library_increment_is_zero_at_the_redundancy_threshold() -> None:
    payload = score_factor(_result(), library_correlation=0.7)
    entry = next(d for d in payload["dimensions"] if d["name"] == "library_increment")
    assert entry["score"] == 0.0


def test_a_negatively_correlated_factor_still_adds_nothing_new() -> None:
    """A mirror image carries the same information, so |corr| is what counts."""
    payload = score_factor(_result(), library_correlation=-0.9)
    entry = next(d for d in payload["dimensions"] if d["name"] == "library_increment")
    assert entry["score"] == 0.0
    assert entry["raw"] == pytest.approx(0.9)


# ── tiers ───────────────────────────────────────────────────────────────

def test_tier_thresholds() -> None:
    assert assign_tier(80.0) == "A"
    assert assign_tier(80.0, truth_verified=True) == "S"
    assert assign_tier(56.0) == "A"
    assert assign_tier(45.0) == "B"
    assert assign_tier(10.0) == "C"
    assert assign_tier(float("nan")) == "C"


def test_truth_verification_alone_does_not_buy_a_tier() -> None:
    """S needs truth-compare AND a high composite."""
    assert assign_tier(60.0, truth_verified=True) == "A"


def test_batch_counts_tiers() -> None:
    batch = score_batch([_result("a"), _result("b", ic=0.011, ic_ir=0.05, t_stat=1.7,
                                           train_ic=0.05, gross=0.02, net=0.019,
                                           turnover=1.0, style_retention=0.5)])
    assert sum(batch["tier_counts"].values()) == batch["n_scored"]
    assert batch["factors"][0]["composite"] >= batch["factors"][1]["composite"]


def test_card_weights_sum_to_one_hundred() -> None:
    assert TOTAL_WEIGHT == 100
    assert [d.name for d in SCORE_CARD][0] == "ic_stability", "IC stability carries the top weight"
    assert max(d.weight for d in SCORE_CARD) == 20


# ── clustering ──────────────────────────────────────────────────────────

def _corr(names: list[str], blocks: list[list[float]]) -> pd.DataFrame:
    return pd.DataFrame(blocks, index=names, columns=names)


def test_clustering_groups_highly_correlated_factors() -> None:
    names = ["a", "b", "c", "d"]
    matrix = _corr(
        names,
        [
            [1.0, 0.9, 0.1, 0.05],
            [0.9, 1.0, 0.15, 0.1],
            [0.1, 0.15, 1.0, 0.85],
            [0.05, 0.1, 0.85, 1.0],
        ],
    )
    result = cluster_factors(matrix, threshold=0.7)
    assert result["n_clusters"] == 2
    membership = {frozenset(c["members"]) for c in result["clusters"]}
    assert frozenset({"a", "b"}) in membership
    assert frozenset({"c", "d"}) in membership


def test_clustering_treats_a_mirror_image_as_the_same_information() -> None:
    names = ["a", "b"]
    matrix = _corr(names, [[1.0, -0.95], [-0.95, 1.0]])
    result = cluster_factors(matrix, threshold=0.7)
    assert result["n_clusters"] == 1


def test_clustering_respects_the_threshold() -> None:
    names = ["a", "b"]
    matrix = _corr(names, [[1.0, 0.6], [0.6, 1.0]])
    assert cluster_factors(matrix, threshold=0.7)["n_clusters"] == 2
    assert cluster_factors(matrix, threshold=0.5)["n_clusters"] == 1


def test_clustering_reports_intra_cluster_correlation() -> None:
    names = ["a", "b"]
    matrix = _corr(names, [[1.0, 0.8], [0.8, 1.0]])
    cluster = cluster_factors(matrix, threshold=0.7)["clusters"][0]
    assert cluster["mean_intra_correlation"] == pytest.approx(0.8)
    assert cluster["max_intra_correlation"] == pytest.approx(0.8)


def test_clustering_treats_nan_pairs_as_unrelated() -> None:
    """A data gap must not silently merge two clusters."""
    names = ["a", "b"]
    matrix = _corr(names, [[1.0, np.nan], [np.nan, 1.0]])
    assert cluster_factors(matrix, threshold=0.7)["n_clusters"] == 2


def test_clustering_rejects_a_mismatched_matrix() -> None:
    matrix = pd.DataFrame([[1.0]], index=["a"], columns=["b"])
    with pytest.raises(ScoringError, match="identical index and columns"):
        cluster_factors(matrix)


def test_clustering_rejects_an_invalid_threshold() -> None:
    matrix = _corr(["a"], [[1.0]])
    for bad in (0.0, 1.0, -0.2):
        with pytest.raises(ValueError, match="threshold must lie"):
            cluster_factors(matrix, threshold=bad)


def test_clustering_handles_an_empty_matrix() -> None:
    empty = pd.DataFrame(index=[], columns=[], dtype=float)
    assert cluster_factors(empty)["n_clusters"] == 0


# ── representatives ─────────────────────────────────────────────────────

def test_representative_is_the_highest_scoring_member() -> None:
    clusters = [{"cluster_id": "C000", "members": ["a", "b", "c"], "size": 3}]
    scores = {"a": {"composite": 50.0}, "b": {"composite": 80.0}, "c": {"composite": 60.0}}
    chosen = select_representatives(clusters, scores)
    assert chosen[0]["representative"] == "b"


def test_ties_are_broken_by_lower_turnover() -> None:
    clusters = [{"cluster_id": "C000", "members": ["a", "b"], "size": 2}]
    scores = {"a": {"composite": 70.0}, "b": {"composite": 70.0}}
    chosen = select_representatives(clusters, scores, turnover={"a": 0.5, "b": 0.1})
    assert chosen[0]["representative"] == "b"


def test_further_ties_are_deterministic() -> None:
    clusters = [{"cluster_id": "C000", "members": ["b", "a"], "size": 2}]
    scores = {"a": {"composite": 70.0}, "b": {"composite": 70.0}}
    assert select_representatives(clusters, scores)[0]["representative"] == "a"


def test_unscored_members_still_produce_a_representative() -> None:
    clusters = [{"cluster_id": "C000", "members": ["a", "b"], "size": 2}]
    chosen = select_representatives(clusters, {})
    assert chosen[0]["representative"] == "a"
    assert chosen[0]["scored_members"] == 0


def test_representatives_carry_the_cluster_structure() -> None:
    clusters = [
        {
            "cluster_id": "C000",
            "members": ["a", "b"],
            "size": 2,
            "mean_intra_correlation": 0.81,
        }
    ]
    chosen = select_representatives(clusters, {"a": {"composite": 1.0}})
    assert chosen[0]["cluster_id"] == "C000"
    assert chosen[0]["mean_intra_correlation"] == 0.81
    assert chosen[0]["members"] == ["a", "b"]
