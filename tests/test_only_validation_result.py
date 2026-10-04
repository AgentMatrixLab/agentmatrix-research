"""TEST-ONLY tests for reading the frozen validator's result shape.

Regression guard for a bug that would have been silent and expensive: the frozen
validator keys rank-IC statistics as ``"10d"``, and a consumer looking up
``"10"`` finds nothing. Because the batch report swallowed that, a run over 900
factors would have reported "0 passed FDR" -- indistinguishable from a working
correction that simply rejected everything.
"""

from __future__ import annotations

import math

import pytest

from research_core.factor_lab.validation_result import (
    ValidationResultError,
    extract_rank_ic_statistic,
    horizon_keys,
    resolve_primary_horizon,
    resolve_rank_ic_entry,
)


def _result(**overrides) -> dict:
    """A result shaped exactly like the frozen validator writes it."""
    payload = {
        "factor_id": "reversal_1m",
        "rank_ic": {
            "5d": {"mean": 0.01, "ic_ir": 0.2, "t_stat": 1.2, "days": 420, "yearly": {}},
            "10d": {"mean": 0.02, "ic_ir": 0.4, "t_stat": 2.7, "days": 420, "yearly": {}},
            "20d": {"mean": 0.03, "ic_ir": 0.5, "t_stat": 3.1, "days": 420, "yearly": {}},
        },
    }
    payload.update(overrides)
    return payload


# ── the key shape ───────────────────────────────────────────────────────

def test_the_validator_d_key_shape_is_resolved() -> None:
    entry = resolve_rank_ic_entry(_result(), 10)
    assert entry is not None
    assert entry["t_stat"] == 2.7


def test_extract_reads_the_d_keyed_statistic() -> None:
    assert extract_rank_ic_statistic(_result(), 10) == (2.7, 420)


def test_horizon_keys_offer_the_d_form_first() -> None:
    keys = horizon_keys(10)
    assert keys[0] == "10d"
    assert "10" in keys


def test_bare_integer_keys_still_work() -> None:
    """Hand-written fixtures use the bare form; they must keep working."""
    payload = {"factor_id": "f", "rank_ic": {"10": {"t_stat": 2.0, "days": 100}}}
    assert extract_rank_ic_statistic(payload, 10) == (2.0, 100)


def test_primary_horizon_is_read_from_a_declaration() -> None:
    assert resolve_primary_horizon(_result(primary_horizon=20)) == 20


def test_primary_horizon_defaults_to_ten_when_present() -> None:
    assert resolve_primary_horizon(_result()) == 10


def test_primary_horizon_adapts_when_only_one_exists() -> None:
    payload = {"factor_id": "f", "rank_ic": {"20d": {"t_stat": 2.0, "days": 100}}}
    assert resolve_primary_horizon(payload) == 20


def test_a_single_horizon_is_used_even_when_the_number_differs() -> None:
    payload = {"factor_id": "f", "rank_ic": {"20d": {"t_stat": 2.0, "days": 100}}}
    assert resolve_rank_ic_entry(payload, 10)["t_stat"] == 2.0


# ── failure modes must be loud, not silent ──────────────────────────────

def test_a_missing_table_raises_rather_than_reporting_zero() -> None:
    with pytest.raises(ValidationResultError, match="no rank_ic table"):
        extract_rank_ic_statistic({"factor_id": "f"}, 10)


def test_an_ambiguous_table_names_the_keys_it_has() -> None:
    payload = {"factor_id": "f", "rank_ic": {"5d": {"t_stat": 1.0}, "20d": {"t_stat": 3.0}}}
    with pytest.raises(ValidationResultError, match="5d"):
        resolve_rank_ic_entry(payload, 10)


def test_the_error_names_the_factor() -> None:
    with pytest.raises(ValidationResultError, match="MY_FACTOR"):
        extract_rank_ic_statistic({"factor_id": "MY_FACTOR"}, 10)


def test_an_unreadable_t_stat_becomes_nan_rather_than_raising() -> None:
    """A malformed statistic is untestable, not a crash."""
    for bad in (None, "n/a", [], {}):
        payload = {"factor_id": "f", "rank_ic": {"10d": {"t_stat": bad, "days": 10}}}
        t_stat, days = extract_rank_ic_statistic(payload, 10)
        assert math.isnan(t_stat), bad
        assert days == 10


def test_an_unreadable_day_count_becomes_zero() -> None:
    payload = {"factor_id": "f", "rank_ic": {"10d": {"t_stat": 2.0, "days": "many"}}}
    t_stat, days = extract_rank_ic_statistic(payload, 10)
    assert t_stat == 2.0
    assert days == 0


def test_a_negative_day_count_is_clamped() -> None:
    payload = {"factor_id": "f", "rank_ic": {"10d": {"t_stat": 2.0, "days": -5}}}
    assert extract_rank_ic_statistic(payload, 10) == (2.0, 0)


# ── the bug that motivated this module ──────────────────────────────────

def test_fdr_is_not_a_silent_zero_on_realistically_shaped_results() -> None:
    """The end-to-end regression: real key shape in, real discoveries out."""
    from research_core.factor_lab.supplementary import build_supplementary_report

    results = [
        {"factor_id": "strong", "rank_ic": {"10d": {"t_stat": 8.0, "days": 420}}},
        {"factor_id": "weak", "rank_ic": {"10d": {"t_stat": 0.4, "days": 420}}},
    ]
    report = build_supplementary_report(results, q=0.05)
    assert report["summary"]["n_tested"] == 2, "the d-keyed statistics were not read"
    assert report["summary"]["n_accepted"] == 1

    by_id = {item["factor_id"]: item for item in report["factors"]}
    assert not math.isnan(by_id["strong"]["p_value"])
    assert by_id["strong"]["fdr_accepted"] is True
    assert by_id["weak"]["fdr_accepted"] is False
