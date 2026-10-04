"""TEST-ONLY tests for catalog readiness classification.

These assert the *classifier's* behaviour on hand-written expressions. They are
not evidence about any factor's predictive power, and the synthetic expressions
below are not market data.
"""

from __future__ import annotations

from research_core.factor_lab.catalog_readiness import (
    ALIAS_MAP,
    SUPPORTED_OPERATORS,
    classify_expression,
    readiness_summary,
)


def test_bare_lowercase_expression_is_runnable_now() -> None:
    result = classify_expression("rank(delta(log(volume), 2))")
    assert result.verdict == "runnable_now"
    assert result.runnable
    assert result.unresolved_operators == ()
    assert result.aliased_operators == ()


def test_dollar_sigil_is_accepted() -> None:
    """The Qlib-style $field sigil must not by itself block classification."""
    result = classify_expression("Mean($close, 5)")
    assert result.verdict == "runnable_now"
    assert "CLOSE" in result.fields_used
    assert result.unresolved_operators == ()


def test_ref_maps_to_ts_delay_not_delta() -> None:
    """Ref is a level shift; aliasing it to Delta would silently change values."""
    result = classify_expression("Ref($close, 5)")
    assert result.verdict == "alias_only"
    assert "REF" in result.aliased_operators
    assert ALIAS_MAP["REF"] == "ts_delay"

    # The registry resolves DELTA to a *difference*; the two must stay distinct.
    from research_core.factor_lab.formula_compiler import _PANEL_OPERATORS

    assert _PANEL_OPERATORS["DELTA"][0] == "ts_delta"
    assert ALIAS_MAP["REF"] != _PANEL_OPERATORS["DELTA"][0]


def test_correlation_synonym_is_alias_resolvable() -> None:
    result = classify_expression("Correlation(rank($volume), rank($close), 6)")
    assert result.verdict == "alias_only"
    assert "CORRELATION" in result.aliased_operators


def test_unimplemented_operator_reports_needs_numerics() -> None:
    result = classify_expression("EMA($close, 12)")
    assert result.verdict == "needs_numerics"
    assert not result.runnable
    assert result.unresolved_operators == ("EMA",)


def test_unknown_operator_must_not_be_silently_accepted() -> None:
    """compile_formula emits unknown calls verbatim; the classifier must not."""
    result = classify_expression("NotARealOperator($close, 5)")
    assert result.verdict == "needs_numerics"
    assert "NOTAREALOPERATOR" in result.unresolved_operators
    assert not result.runnable


def test_ternary_question_mark_syntax_is_unparsable() -> None:
    """WorldQuant's `?:` is not in the grammar; it must be reported, not guessed."""
    result = classify_expression("(returns < 0) ? stddev(returns, 20) : close")
    assert result.verdict == "unparsable"
    assert result.parse_error is not None


def test_unsupported_field_is_surfaced() -> None:
    result = classify_expression("$no_such_field / $close")
    assert "NO_SUCH_FIELD" in result.missing_fields


def test_panel_field_is_not_reported_missing() -> None:
    result = classify_expression("$close*$volume")
    assert result.missing_fields == ()


def test_open_high_low_are_derived_not_missing() -> None:
    """OHLC is not in the frozen panel contract but is derivable from RQData."""
    result = classify_expression("($high-$low)/$open")
    assert result.missing_fields == ()
    assert {"HIGH", "LOW", "OPEN"} <= set(result.fields_used)


def test_summary_counts_and_ranks_blockers() -> None:
    verdicts = [
        classify_expression("rank($close)"),
        classify_expression("Ref($close, 5)"),
        classify_expression("EMA($close, 12)"),
        classify_expression("EMA($close, 26)"),
        classify_expression("(? bad"),
    ]
    summary = readiness_summary(verdicts)

    assert summary["total"] == 5
    assert summary["counts"]["runnable_now"] == 1
    assert summary["counts"]["alias_only"] == 1
    assert summary["counts"]["needs_numerics"] == 2
    assert summary["counts"]["unparsable"] == 1
    assert summary["runnable"] == 2
    assert summary["runnable_ratio"] == 2 / 5
    # EMA blocks two expressions, so it must rank first.
    assert next(iter(summary["operator_blockers"])) == "EMA"


def test_alias_keys_are_disjoint_from_registered_operators() -> None:
    """An already-registered spelling must not also be aliased.

    Shadowing a registry key would let a future rename change what an existing
    catalog expression computes without any test noticing. Checked in normalised
    form, because that is the form resolution actually uses.
    """
    from research_core.factor_lab.catalog_readiness import normalise_operator

    collisions = sorted(
        normalise_operator(k)
        for k in set(ALIAS_MAP) & SUPPORTED_OPERATORS
    )
    assert collisions == [], f"aliases shadow registered operators: {collisions}"


def test_long_form_ts_spellings_resolve() -> None:
    """The catalog's Ts_*/TS_* spellings must not silently become blockers.

    Regression guard: TS_MEAN/TS_STD/TS_MIN/TS_MAX are *not* registry keys, so
    dropping them from ALIAS_MAP would push real catalog factors into
    `needs_numerics` while every other test still passed.
    """
    for spelling in (
        "Ts_Mean($close, 5)",
        "Ts_Std($close, 5)",
        "Ts_Min($low, 5)",
        "Ts_Max($high, 5)",
        "Ts_Sum($volume, 5)",
        "Ts_Rank($close, 5)",
        "Ts_ArgMax($high, 5)",
        "Ts_ArgMin($low, 5)",
        "Ts_DecayLinear($close, 5)",
        "TS_DECAY_LINEAR($close, 5)",
        "DecayLinear($close, 5)",
        "Ts_Mean($close, 5)",
        "Ts_Product($volume, 3)",
    ):
        result = classify_expression(spelling)
        assert result.runnable, f"{spelling} unresolved: {result.unresolved_operators}"


def test_operator_normalisation_folds_case_and_underscores() -> None:
    from research_core.factor_lab.catalog_readiness import normalise_operator

    assert normalise_operator("Ts_DecayLinear") == normalise_operator("TS_DECAY_LINEAR")
    assert normalise_operator("ts_rank") == normalise_operator("Ts_Rank")
    # Distinct operations must stay distinct after folding.
    assert normalise_operator("Ts_Min") != normalise_operator("Ts_Max")
    assert normalise_operator("Ref") != normalise_operator("Rank")
