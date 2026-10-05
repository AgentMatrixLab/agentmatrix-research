"""TEST-ONLY tests for the candidate-list builder.

`primary_window` decides which parameter the perturbation gate varies, so its
convention is pinned here rather than left to the implementation. Synthetic
expressions only.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_candidate_list as builder  # noqa: E402

from research_core.factor_lab.batch_validation import load_candidate_list  # noqa: E402


# ── window extraction ───────────────────────────────────────────────────

def test_a_single_window_is_extracted() -> None:
    assert builder.primary_window("Mean($close, 20)") == 20


def test_the_trailing_window_argument_is_the_one_taken() -> None:
    """The first literal is often a lag, not the window."""
    assert builder.primary_window("Corr($close, $volume, 15)") == 15


def test_a_windowless_expression_has_no_window() -> None:
    assert builder.primary_window("$close / $open") is None


def test_the_most_frequent_window_wins() -> None:
    """`Mean(x,5)` twice and `Mean(x,10)` once -> 5 is the factor's own parameter."""
    assert builder.primary_window("Mean($close, 5) + Mean($volume, 5) * Mean($open, 10)") == 5


def test_ties_go_to_the_smaller_window() -> None:
    assert builder.primary_window("Mean($close, 10) + Mean($volume, 5)") == 5


def test_an_exponent_is_not_mistaken_for_a_window() -> None:
    """`SignedPower(x, 2)` takes an exponent, not a window."""
    assert builder.primary_window("SignedPower($close, 2)") is None


def test_a_bare_literal_outside_a_window_operator_is_ignored() -> None:
    assert builder.primary_window("$close * 100") is None


def test_the_same_window_in_nested_operators_is_counted_once_per_call() -> None:
    assert builder.primary_window("Mean(Std($close, 20), 20)") == 20


def test_an_unparsable_expression_yields_no_window() -> None:
    assert builder.primary_window("Mean($close, ") is None


def test_a_ref_delay_counts_as_a_window() -> None:
    assert builder.primary_window("Ref($close, 5)") == 5


# ── row building ────────────────────────────────────────────────────────

def _factor(factor_id: str, expression: str, name_cn: str = "名") -> dict:
    return {"factor_id": factor_id, "formula_expr": expression, "name_cn": name_cn,
            "category": "技术因子"}


def test_risk_families_are_flagged_not_dropped() -> None:
    """The ruling: exposures run and report, but never count as alpha."""
    rows, report = builder.build_rows(
        [
            _factor("BARRA:size", "Mean($close, 20)"),
            _factor("ALPHA158:KMID", "Mean(($close-$open)/$open, 20)"),
        ],
        include_not_runnable=False,
    )
    by_id = {row["factor_id"]: row for row in rows}
    assert by_id["BARRA:size"]["risk_exposure"] == "true"
    assert by_id["ALPHA158:KMID"]["risk_exposure"] == "false"
    assert report["stats"]["risk_exposure"] == 1
    assert len(rows) == 2, "a flagged exposure is still a candidate"


def _unimplemented_operator() -> str:
    """Pick an operator the engine genuinely does not resolve.

    Derived from the registry rather than hard-coded, so implementing an operator
    later does not turn these tests into silent no-ops.
    """
    from research_core.factor_lab.formula_compiler import _OPERATOR_INDEX, resolve_operator_name

    for candidate in ("VPT", "ADX", "ADXR", "MASS", "PDI", "MDI", "WR", "OBV", "DPO", "NOTREAL"):
        if resolve_operator_name(candidate) not in _OPERATOR_INDEX.values():
            return candidate
    raise AssertionError("every candidate is now implemented; extend the list")


def test_uncomputable_factors_are_omitted_by_default() -> None:
    blocked = f"{_unimplemented_operator()}($close, 12)"
    rows, report = builder.build_rows(
        [_factor("X:ok", "Mean($close, 20)"), _factor("X:bad", blocked)],
        include_not_runnable=False,
    )
    assert [row["factor_id"] for row in rows] == ["X:ok"]
    assert report["stats"]["skipped_not_runnable"] == 1
    assert any(factor_id == "X:bad" for factor_id, _ in report["skipped"])


def test_uncomputable_factors_can_be_included_explicitly() -> None:
    """The blocked operator is not a window operator, so its factor is windowless too.

    Both exclusions have to be lifted for the row to appear, which is the point:
    a factor the engine cannot compute is refused for two independent reasons.
    """
    blocked = f"{_unimplemented_operator()}($close, 12)"
    rows, _ = builder.build_rows(
        [_factor("X:bad", blocked)],
        include_not_runnable=True,
        include_windowless=True,
    )
    assert [row["factor_id"] for row in rows] == ["X:bad"]


def test_windowless_candidates_are_excluded_by_default() -> None:
    """Structural, not a threshold.

    The factor file's sidecar requires a positive integer window for every
    declared factor, so a windowless candidate cannot be represented in it and the
    validator cannot obtain a base window. Leaving it in the candidate list would
    make validate-batch error on a factor missing from the factor file.
    """
    rows, report = builder.build_rows(
        [_factor("X:w", "Mean($close, 20)"), _factor("X:now", "$close / $open")],
        include_not_runnable=False,
    )
    assert [row["factor_id"] for row in rows] == ["X:w"]
    assert report["stats"]["skipped_windowless"] == 1
    assert any("no window" in reason for _, reason in report["skipped"])


def test_windowless_candidates_can_be_emitted_for_inspection() -> None:
    rows, report = builder.build_rows(
        [_factor("X:now", "$close / $open")],
        include_not_runnable=False,
        include_windowless=True,
    )
    assert [row["factor_id"] for row in rows] == ["X:now"]
    assert report["stats"]["with_window"] == 0
    assert report["stats"]["without_window"] == 1


def test_required_fields_come_from_the_classifier() -> None:
    rows, _ = builder.build_rows(
        [_factor("X:f", "Mean(($high-$low)/$open, 20)")], include_not_runnable=False
    )
    fields = set(rows[0]["required_fields"].split(";"))
    assert {"HIGH", "LOW", "OPEN"} <= fields


# ── the written file must satisfy the real contract ─────────────────────

def test_the_written_list_loads_through_the_batch_validator(tmp_path: Path) -> None:
    rows, _ = builder.build_rows(
        [
            _factor("X:a", "Mean($close, 20)"),
            _factor("X:b", "Mean(($close-$open)/$open, 5)"),
        ],
        include_not_runnable=False,
    )
    path = tmp_path / "candidate_list.csv"
    import csv

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(builder.COLUMNS))
        writer.writeheader()
        writer.writerows(rows)

    candidates = load_candidate_list(path)
    assert [c.factor_id for c in candidates] == ["X:a", "X:b"]
    assert candidates[0].window == 20
    assert candidates[1].window == 5
    assert all(c.risk_exposure is False for c in candidates)


def test_a_windowless_row_survives_the_round_trip_when_explicitly_emitted(tmp_path: Path) -> None:
    """The loader accepts an empty window; the factor *file* is what cannot."""
    rows, _ = builder.build_rows(
        [_factor("X:now", "$close / $open")],
        include_not_runnable=False,
        include_windowless=True,
    )
    path = tmp_path / "candidate_list.csv"
    import csv

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(builder.COLUMNS))
        writer.writeheader()
        writer.writerows(rows)

    candidates = load_candidate_list(path)
    assert [c.factor_id for c in candidates] == ["X:now"]
    assert candidates[0].window is None


def test_the_column_set_is_frozen() -> None:
    assert builder.COLUMNS == (
        "factor_id", "name", "formula", "category", "required_fields",
        "direction", "risk_exposure", "window",
    )


def test_risk_families_are_the_declared_ones() -> None:
    assert builder.RISK_FAMILIES == {"BARRA", "JQGM"}
