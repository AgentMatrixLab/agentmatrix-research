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
    normalise_operator,
    readiness_summary,
    resolve_operator,
)
from research_core.factor_lab.formula_compiler import (
    UnsupportedOperatorError,
    compile_formula,
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
    assert resolve_operator("Ref") == "TS_DELAY"

    from research_core.factor_lab.formula_compiler import _PANEL_OPERATORS

    # DELTA resolves to a *difference*; the two must stay distinct.
    assert _PANEL_OPERATORS["DELTA"][0] == "ts_delta"
    assert _PANEL_OPERATORS["TS_DELAY"][0] == "ts_delay"


def test_correlation_synonym_is_alias_resolvable() -> None:
    result = classify_expression("Correlation(rank($volume), rank($close), 6)")
    assert result.verdict == "alias_only"
    assert "CORRELATION" in result.aliased_operators


def _unimplemented_operator() -> str:
    """Pick an operator the engine genuinely does not resolve.

    Derived from the registry rather than hard-coded, so implementing an
    operator later does not silently turn these tests into no-ops or failures.
    """
    from research_core.factor_lab.formula_compiler import (
        _OPERATOR_INDEX,
        resolve_operator_name,
    )

    for candidate in (
        "VPT", "ADX", "ADXR", "MASS", "PDI", "MDI", "WR", "OBV",
        "DPO", "ULTOSC", "SAR", "NOTAREALOPERATOR",
    ):
        if resolve_operator_name(candidate) not in _OPERATOR_INDEX.values():
            return candidate
    raise AssertionError("every candidate is now implemented; extend the list")


def test_unimplemented_operator_reports_needs_numerics() -> None:
    name = _unimplemented_operator()
    result = classify_expression(f"{name}($close, 12)")
    assert result.verdict == "needs_numerics"
    assert not result.runnable
    assert result.unresolved_operators == (name,)


def test_unknown_operator_is_not_silently_accepted() -> None:
    result = classify_expression("NotARealOperator($close, 5)")
    assert result.verdict == "needs_numerics"
    assert "NOTAREALOPERATOR" in result.unresolved_operators
    assert not result.runnable


def test_classifier_and_compiler_agree_on_what_is_computable() -> None:
    """The two must never disagree: the classifier predicts engine behaviour."""
    runnable = [
        "Rank($close)",
        "Ref($close, 5)",
        "Ts_Mean($close, 5)",
        "Correlation(rank($close), rank($volume), 6)",
        "Power($close, 2)",
        "IndNeutral($close, industry)",
        "EMA($close, 12)",
        "Quantile($close, 20, 0.8)",
        "ATR($close, $high, $low, 14)",
    ]
    blocked = [f"{_unimplemented_operator()}($close, 12)", "NotARealOperator($close, 5)"]

    for expression in runnable:
        assert classify_expression(expression).runnable, expression
        compile_formula(expression)  # must not raise

    for expression in blocked:
        assert not classify_expression(expression).runnable, expression
        try:
            compile_formula(expression)
        except UnsupportedOperatorError:
            continue
        raise AssertionError(f"{expression} compiled but was classified as blocked")


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
    name = _unimplemented_operator()
    verdicts = [
        classify_expression("rank($close)"),
        classify_expression("Ref($close, 5)"),
        classify_expression(f"{name}($close, 12)"),
        classify_expression(f"{name}($close, 24)"),
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
    # The blocker appears in two expressions, so it must rank first.
    assert next(iter(summary["operator_blockers"])) == name


def test_alias_keys_are_disjoint_from_registered_operators() -> None:
    """An already-registered spelling must not also be aliased.

    Shadowing a registry key would let a future rename change what an existing
    catalog expression computes without any test noticing. Checked in normalised
    form, because that is the form resolution actually uses.
    """
    collisions = sorted(k for k in ALIAS_MAP if k in {normalise_operator(n) for n in SUPPORTED_OPERATORS})
    assert collisions == [], f"aliases shadow registered operators: {collisions}"


def test_long_form_ts_spellings_resolve() -> None:
    """The catalog's Ts_*/TS_* spellings must not silently become blockers.

    Regression guard: TS_MEAN/TS_STD/TS_MIN/TS_MAX are *not* registry keys, so
    losing them from the alias table would push real catalog factors into
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
        "Ts_Product($volume, 3)",
        "StdDev($close, 20)",
        "Covariance($close, $volume, 6)",
        "SignedPower($close, 2)",
        "IndNeutral($close, industry)",
    ):
        result = classify_expression(spelling)
        assert result.runnable, f"{spelling} unresolved: {result.unresolved_operators}"


def test_operator_normalisation_folds_case_and_underscores() -> None:
    assert normalise_operator("Ts_DecayLinear") == normalise_operator("TS_DECAY_LINEAR")
    assert normalise_operator("ts_rank") == normalise_operator("Ts_Rank")
    # Distinct operations must stay distinct after folding.
    assert normalise_operator("Ts_Min") != normalise_operator("Ts_Max")
    assert normalise_operator("Ref") != normalise_operator("Rank")
    assert normalise_operator("Power") != normalise_operator("SignedPower")


def test_greater_and_less_are_elementwise_max_and_min() -> None:
    """Verified against GTJA191 usage; they are NOT boolean selectors.

    GTJA003 needs ``Less(LOW, DELAY(CLOSE,1))`` to be ``MIN(LOW, prev close)``
    and ``Greater(HIGH, DELAY(CLOSE,1))`` to be ``MAX(HIGH, prev close)``;
    GTJA052 needs ``Greater(x, 0)`` to clamp at zero; GTJA077 needs
    ``Less(RANK(a), RANK(b))`` to be the smaller of two ranks.
    """
    import numpy as np
    import pandas as pd

    from research_core.factor_lab.formula_compiler import _SERIES_OPERATORS

    assert _SERIES_OPERATORS["GREATER"] == "np.maximum"
    assert _SERIES_OPERATORS["LESS"] == "np.minimum"

    left = pd.Series([1.0, 5.0, -3.0])
    right = pd.Series([2.0, 2.0, 0.0])
    assert list(np.maximum(left, right)) == [2.0, 5.0, 0.0]
    assert list(np.minimum(left, right)) == [1.0, 2.0, -3.0]

    for spelling in ("Greater($close, $open)", "Less($close, $open)"):
        assert classify_expression(spelling).runnable, spelling


def test_greater_does_not_shadow_the_rolling_max() -> None:
    """GREATER is element-wise; MAX is a rolling-window operator."""
    from research_core.factor_lab.formula_compiler import _PANEL_OPERATORS

    assert _PANEL_OPERATORS["MAX"][0] == "ts_max"
    assert "GREATER" not in _PANEL_OPERATORS
    assert normalise_operator("Greater") != normalise_operator("Max")


def test_power_and_signed_power_stay_distinct() -> None:
    """Power is x**a; SignedPower is sign(x)*|x|**a. They differ for x < 0."""
    from research_core.factor_lab.formula_compiler import _SERIES_OPERATORS

    assert _SERIES_OPERATORS["POWER"] != _SERIES_OPERATORS["SIGNED_POWER"]
    assert _SERIES_OPERATORS["POWER"] == "np.power"
    assert _SERIES_OPERATORS["SIGNED_POWER"] == "signed_power"


def test_power_is_not_signed_power_on_negative_inputs() -> None:
    """A numeric guard on the distinction, so the two can never be merged."""
    import numpy as np
    import pandas as pd

    from research_core.factor_lab.operators import signed_power

    values = pd.Series([-2.0, 2.0])
    assert np.allclose(signed_power(values, 2.0), [-4.0, 4.0])
    assert np.allclose(np.power(values, 2.0), [4.0, 4.0])
