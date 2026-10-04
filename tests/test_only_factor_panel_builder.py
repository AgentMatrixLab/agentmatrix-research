"""TEST-ONLY tests for the Factor Console dataset builder.

These guard the *panel's internal consistency* against the repository artifacts it
reads. They say nothing about factor quality; the panel is a delivery-status
instrument, and a silently wrong number on it is worse than a missing one.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_factor_panel import TARGET_FACTORS, build_payload  # noqa: E402

VALID_READINESS = {"runnable_now", "alias_only", "needs_numerics", "unparsable"}
VALID_STATUS = {"real", "computed", "not_run", "placeholder", "not_implemented"}


@pytest.fixture(scope="module")
def payload() -> dict:
    return build_payload()


def test_catalog_total_matches_factor_rows(payload: dict) -> None:
    assert payload["catalog"]["total"] == len(payload["factors"])
    assert payload["catalog"]["total"] > 0


def test_readiness_counts_sum_to_catalog_total(payload: dict) -> None:
    counts = payload["catalog"]["readiness"]["counts"]
    assert set(counts) == VALID_READINESS, "verdict vocabulary drifted"
    assert sum(counts.values()) == payload["catalog"]["total"]


def test_runnable_is_the_sum_of_the_two_runnable_verdicts(payload: dict) -> None:
    summary = payload["catalog"]["readiness"]
    counts = summary["counts"]
    assert summary["runnable"] == counts["runnable_now"] + counts["alias_only"]


def test_every_factor_carries_a_known_verdict(payload: dict) -> None:
    bad = [f["factor_id"] for f in payload["factors"] if f["readiness"] not in VALID_READINESS]
    assert bad == []


def test_blocked_factors_say_why(payload: dict) -> None:
    """A blocked factor must name a blocker; otherwise the panel is unactionable."""
    for factor in payload["factors"]:
        if factor["readiness"] == "needs_numerics":
            assert factor["blocking_operators"], factor["factor_id"]
        if factor["readiness"] == "unparsable":
            assert factor["parse_error"], factor["factor_id"]


def test_funnel_stages_are_well_formed(payload: dict) -> None:
    stages = payload["funnel"]
    assert [s["key"] for s in stages] == [
        "catalog",
        "engine_ready",
        "submitted",
        "validated",
        "scored",
        "strategy",
        "live",
    ]
    for stage in stages:
        assert stage["status"] in VALID_STATUS, stage
        assert isinstance(stage["count"], int) and stage["count"] >= 0, stage
        assert stage["evidence"], stage


def test_funnel_is_monotonic_through_the_production_stages(payload: dict) -> None:
    """You cannot validate more factors than you submitted, etc."""
    by_key = {s["key"]: s["count"] for s in payload["funnel"]}
    assert by_key["submitted"] <= by_key["engine_ready"]
    assert by_key["validated"] <= by_key["submitted"]
    assert by_key["scored"] <= by_key["validated"]
    assert by_key["live"] <= by_key["scored"] + by_key["strategy"]


def test_engine_ready_matches_readiness_summary(payload: dict) -> None:
    by_key = {s["key"]: s["count"] for s in payload["funnel"]}
    assert by_key["engine_ready"] == payload["catalog"]["readiness"]["runnable"]


def test_panel_declares_no_simulated_data(payload: dict) -> None:
    assert payload["honesty"]["simulated_data"] is False
    assert payload["honesty"]["validation_runs_found"] == len(payload["real_runs"])


def test_validated_count_matches_real_runs(payload: dict) -> None:
    passed = sum(1 for r in payload["real_runs"] if r.get("passed"))
    assert payload["delivery"]["validated_factors"] == passed
    assert payload["delivery"]["gap_to_target"] == max(TARGET_FACTORS - passed, 0)


def test_gate_order_matches_the_frozen_config(payload: dict) -> None:
    """The panel must show the frozen gate order, not a copy that can drift."""
    gates = payload["gates"]
    if not gates.get("available"):  # PyYAML absent
        pytest.skip("PyYAML unavailable; gate config not parsed")

    import yaml

    config = yaml.safe_load(
        (ROOT / "configs/validation_gates.yaml").read_text(encoding="utf-8")
    )
    assert gates["order"] == config["gates"]["order"]
    assert gates["split"] == config["split"]
    assert gates["cost"] == config["portfolio"]["cost"]


def test_delivery_target_is_three_hundred(payload: dict) -> None:
    assert payload["delivery"]["target_factors"] == 300
    assert payload["delivery"]["deadline"] == "2026-10-07"
