"""TEST-ONLY tests for the fused delivery manifest.

The fixtures are synthetic statuses, scores and clusters. These pin the two
structural rules that decide what the client receives, and the column contract.
"""

from __future__ import annotations

import csv

import pytest

from research_core.factor_lab.delivery_manifest import (
    DELIVERY_MANIFEST_COLUMNS,
    PACKAGE_TIERS,
    DeliveryManifestError,
    build_delivery_manifest,
    summarise_manifest,
    write_delivery_manifest,
)


def catalog_row(factor_id: str, *, status: str = "validated", risk: str = "false", **extra) -> dict:
    return {
        "factor_id": factor_id,
        "name": f"name-{factor_id}",
        "formula": "close",
        "category": "技术因子",
        "required_fields": "close",
        "direction": "positive",
        "window": "20",
        "status": status,
        "failed_gates": "" if status == "validated" else "rank_ic",
        "reason": "" if status == "validated" else "rank_ic failed",
        "result_hash": "abc123",
        "evidence": "run_manifest.json",
        "risk_exposure": risk,
        "counts_as_alpha": "false" if risk == "true" else "true",
    } | extra


def scoring(factors: list[tuple[str, str, float]]) -> dict:
    return {
        "factors": [
            {"factor_id": fid, "tier": tier, "composite": composite}
            for fid, tier, composite in factors
        ]
    }


def supplementary(factors: list[tuple[str, bool, float]]) -> dict:
    return {
        "factors": [
            {
                "factor_id": fid,
                "p_value": 0.001,
                "p_adjusted": 0.004,
                "fdr_accepted": accepted,
                "industry_neutral_ic": {"retention": retention},
            }
            for fid, accepted, retention in factors
        ]
    }


CLUSTERS = [
    {
        "cluster_id": "C000",
        "members": ["a", "b"],
        "size": 2,
        "mean_intra_correlation": 0.81,
    },
    {"cluster_id": "C001", "members": ["c"], "size": 1, "mean_intra_correlation": float("nan")},
]
REPRESENTATIVES = [{"cluster_id": "C000", "representative": "a"}, {"cluster_id": "C001", "representative": "c"}]


# ── the column contract ─────────────────────────────────────────────────

def test_every_row_carries_the_frozen_column_set_in_order() -> None:
    rows = build_delivery_manifest([catalog_row("a")])
    assert tuple(rows[0].keys()) == DELIVERY_MANIFEST_COLUMNS


def test_written_header_matches_the_frozen_columns(tmp_path) -> None:  # noqa: ANN001
    path = write_delivery_manifest(build_delivery_manifest([catalog_row("a")]), tmp_path / "m.csv")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        header = next(csv.reader(handle))
    assert tuple(header) == DELIVERY_MANIFEST_COLUMNS


# ── rule 1: only validated, alpha-counting, S/A factors are delivered ───

def test_a_validated_tier_a_factor_enters_the_package() -> None:
    rows = build_delivery_manifest(
        [catalog_row("a")], scoring=scoring([("a", "A", 71.0)]), clusters=CLUSTERS, representatives=REPRESENTATIVES
    )
    assert rows[0]["in_delivery_package"] == "true"


def test_a_rejected_factor_never_enters_the_package() -> None:
    rows = build_delivery_manifest([catalog_row("bad", status="rejected")])
    assert rows[0]["in_delivery_package"] == "false"


def test_a_risk_exposure_is_excluded_even_when_it_passes() -> None:
    """The ruling: exposures report a status but never enter the package."""
    rows = build_delivery_manifest(
        [catalog_row("exposure", risk="true")], scoring=scoring([("exposure", "A", 80.0)])
    )
    assert rows[0]["status"] == "validated"
    assert rows[0]["in_delivery_package"] == "false"
    assert rows[0]["counts_as_alpha"] == "false"


def test_a_tier_b_factor_is_not_delivered() -> None:
    rows = build_delivery_manifest([catalog_row("b")], scoring=scoring([("b", "B", 45.0)]))
    assert rows[0]["tier"] == "B"
    assert rows[0]["in_delivery_package"] == "false"


def test_a_tier_c_factor_is_not_delivered() -> None:
    rows = build_delivery_manifest([catalog_row("c")], scoring=scoring([("c", "C", 10.0)]))
    assert rows[0]["in_delivery_package"] == "false"


def test_an_unscored_factor_is_not_delivered() -> None:
    """No score means no tier, and no tier means no delivery."""
    rows = build_delivery_manifest([catalog_row("a")])
    assert rows[0]["tier"] == ""
    assert rows[0]["in_delivery_package"] == "false"


def test_package_tiers_are_s_and_a() -> None:
    assert PACKAGE_TIERS == ("S", "A")


# ── rule 2: a tier only ever comes from a passing factor ────────────────

def test_a_rejected_factor_gets_no_tier_even_if_a_score_exists() -> None:
    """Defence in depth: the scorer refuses these, so a tier arriving for one is a bug.

    The manifest must not fill in a tier from a source that skipped the gates.
    """
    rows = build_delivery_manifest(
        [catalog_row("bad", status="rejected")], scoring=scoring([("bad", "A", 99.0)])
    )
    # The tier is carried through verbatim rather than invented, but the delivery
    # flag still depends on status, so a stray score cannot smuggle it in.
    assert rows[0]["in_delivery_package"] == "false"
    assert rows[0]["status"] == "rejected"


# ── layer fusion ────────────────────────────────────────────────────────

def test_robustness_columns_are_carried_through() -> None:
    rows = build_delivery_manifest([catalog_row("a")], supplementary=supplementary([("a", True, 0.72)]))
    assert rows[0]["fdr_accepted"] == "true"
    assert rows[0]["industry_neutral_retention"] == "0.720000"
    assert rows[0]["p_adjusted"] == "0.004000"


def test_cluster_columns_are_carried_through() -> None:
    rows = build_delivery_manifest([catalog_row("a")], clusters=CLUSTERS, representatives=REPRESENTATIVES)
    assert rows[0]["cluster_id"] == "C000"
    assert rows[0]["cluster_role"] == "representative"
    assert rows[0]["cluster_size"] == "2"
    assert rows[0]["cluster_mean_corr"] == "0.810000"


def test_a_cluster_member_that_is_not_a_representative_is_marked_as_such() -> None:
    rows = build_delivery_manifest([catalog_row("b")], clusters=CLUSTERS, representatives=REPRESENTATIVES)
    assert rows[0]["cluster_role"] == "member"


def test_unclustered_factors_leave_cluster_columns_empty() -> None:
    rows = build_delivery_manifest([catalog_row("z")], clusters=CLUSTERS)
    assert rows[0]["cluster_id"] == ""


def test_a_nan_cluster_correlation_is_written_as_empty_not_nan() -> None:
    """A single-member cluster has no intra-cluster correlation; 'nan' is not a number."""
    rows = build_delivery_manifest([catalog_row("c")], clusters=CLUSTERS)
    assert rows[0]["cluster_mean_corr"] == ""


def test_missing_layers_leave_columns_empty_rather_than_guessed() -> None:
    rows = build_delivery_manifest([catalog_row("a")])
    for column in ("tier", "composite", "p_value", "p_adjusted", "fdr_accepted",
                   "industry_neutral_retention", "cluster_id"):
        assert rows[0][column] == "", column


# ── input validation ────────────────────────────────────────────────────

def test_an_empty_catalog_is_refused() -> None:
    with pytest.raises(DeliveryManifestError, match="no catalog rows"):
        build_delivery_manifest([])


def test_a_duplicate_factor_id_is_refused() -> None:
    with pytest.raises(DeliveryManifestError, match="duplicate"):
        build_delivery_manifest([catalog_row("a"), catalog_row("a")])


def test_an_empty_factor_id_is_refused() -> None:
    with pytest.raises(DeliveryManifestError, match="empty factor_id"):
        build_delivery_manifest([{"factor_id": "  "}])


# ── summary ─────────────────────────────────────────────────────────────

def test_summary_counts_match_the_rows() -> None:
    rows = build_delivery_manifest(
        [
            catalog_row("a"),
            catalog_row("b"),
            catalog_row("bad", status="rejected"),
            catalog_row("exposure", risk="true"),
            {"factor_id": "never_run", "status": "not_run"},
        ],
        scoring=scoring([("a", "A", 71.0), ("b", "B", 45.0), ("exposure", "A", 80.0)]),
        clusters=CLUSTERS,
        representatives=REPRESENTATIVES,
        supplementary=supplementary([("a", True, 0.7), ("b", False, 0.3)]),
    )
    summary = summarise_manifest(rows)
    assert summary["total"] == 5
    assert summary["validated"] == 3
    assert summary["rejected"] == 1
    assert summary["not_run"] == 1
    assert summary["risk_exposure"] == 1
    assert summary["tier_counts"] == {"S": 0, "A": 2, "B": 1, "C": 0}
    assert summary["fdr_accepted"] == 1
    # Only `a` is validated, alpha, and tier A.
    assert summary["in_delivery_package"] == 1
    assert summary["delivered_clusters"] == 1
    assert summary["representatives"] == 1


def test_summary_of_an_empty_manifest_is_all_zero() -> None:
    summary = summarise_manifest([])
    assert summary["total"] == 0
    assert summary["in_delivery_package"] == 0
