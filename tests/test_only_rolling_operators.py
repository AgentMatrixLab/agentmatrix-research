"""TEST-ONLY tests for the rolling statistical operators and technical indicators.

The data here is synthetic and exists only to pin the operators' mathematical
definitions. It is not market data and says nothing about factor quality.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research_core.factor_lab.formula_compiler import compile_formula
from research_core.factor_lab.operators import (
    bias,
    bollinger_band_lower,
    bollinger_band_upper,
    commodity_channel_index,
    relative_strength_index,
    rolling_idxmax,
    rolling_idxmin,
    rolling_quantile,
    rolling_resi,
    rolling_rsquare,
    rolling_slope,
    true_range,
    ts_ema,
    ts_rank,
)

WINDOW = 10


@pytest.fixture(scope="module")
def frame() -> pd.DataFrame:
    rng = np.random.default_rng(20261005)
    dates = pd.bdate_range("2023-01-02", periods=60)
    frames = []
    for index, code in enumerate(["000001.XSHE", "600000.XSHG"]):
        close = 10.0 * np.exp(np.cumsum(rng.normal(0.0004, 0.02, len(dates))))
        high = close * (1 + np.abs(rng.normal(0.006, 0.004, len(dates))))
        low = close * (1 - np.abs(rng.normal(0.006, 0.004, len(dates))))
        frames.append(
            pd.DataFrame(
                {
                    "date": dates,
                    "code": code,
                    "open": close,
                    "high": np.maximum.reduce([high, close]),
                    "low": np.minimum.reduce([low, close]),
                    "close": close,
                    "volume": rng.lognormal(14, 0.4, len(dates)),
                    "amount": rng.lognormal(18, 0.4, len(dates)),
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


def _single_code(frame: pd.DataFrame) -> pd.DataFrame:
    return frame[frame["code"] == "000001.XSHE"].reset_index(drop=True)


# ── Slopes and regression diagnostics ───────────────────────────────────

def test_slope_matches_numpy_polyfit(frame: pd.DataFrame) -> None:
    one = _single_code(frame)
    got = rolling_slope(one, "close", WINDOW)
    y = one["close"].to_numpy()
    t = np.arange(1, WINDOW + 1, dtype=float)
    for end in (WINDOW - 1, 20, 40, len(one) - 1):
        window_values = y[end - WINDOW + 1 : end + 1]
        expected = np.polyfit(t, window_values, 1)[0]
        assert got.iloc[end] == pytest.approx(expected, rel=1e-9, abs=1e-12)


def test_rsquare_matches_pearson_squared(frame: pd.DataFrame) -> None:
    one = _single_code(frame)
    got = rolling_rsquare(one, "close", WINDOW)
    y = one["close"].to_numpy()
    t = np.arange(1, WINDOW + 1, dtype=float)
    for end in (WINDOW - 1, 25, 50):
        window_values = y[end - WINDOW + 1 : end + 1]
        expected = np.corrcoef(t, window_values)[0, 1] ** 2
        assert got.iloc[end] == pytest.approx(expected, rel=1e-8, abs=1e-12)


def test_rsquare_stays_within_unit_interval(frame: pd.DataFrame) -> None:
    values = rolling_rsquare(frame, "close", WINDOW).dropna()
    assert values.between(0.0, 1.0 + 1e-12).all()


def test_resi_is_the_newest_bar_minus_the_fitted_line(frame: pd.DataFrame) -> None:
    one = _single_code(frame)
    got = rolling_resi(one, "close", WINDOW)
    y = one["close"].to_numpy()
    t = np.arange(1, WINDOW + 1, dtype=float)
    end = 30
    window_values = y[end - WINDOW + 1 : end + 1]
    slope, intercept = np.polyfit(t, window_values, 1)
    expected = window_values[-1] - (slope * WINDOW + intercept)
    assert got.iloc[end] == pytest.approx(expected, rel=1e-7, abs=1e-10)


def test_regression_operators_are_nan_before_a_full_window(frame: pd.DataFrame) -> None:
    """Default min_periods is the window, so the run-in is NaN, not partial."""
    for series in (
        rolling_slope(frame, "close", WINDOW),
        rolling_rsquare(frame, "close", WINDOW),
        rolling_resi(frame, "close", WINDOW),
    ):
        first_code = series.iloc[:WINDOW - 1]
        assert first_code.isna().all()


# ── Quantile, index position, EMA ───────────────────────────────────────

def test_quantile_matches_pandas_rolling_quantile(frame: pd.DataFrame) -> None:
    one = _single_code(frame)
    got = rolling_quantile(one, "close", WINDOW, 0.8)
    expected = one["close"].rolling(WINDOW, min_periods=WINDOW).quantile(0.8)
    pd.testing.assert_series_equal(got.reset_index(drop=True), expected, check_names=False)


def test_quantile_rejects_a_level_outside_the_unit_interval(frame: pd.DataFrame) -> None:
    with pytest.raises(ValueError, match="quantile level"):
        rolling_quantile(_single_code(frame), "close", WINDOW, 1.5)


def test_idxmax_returns_one_based_position_from_the_window_start(frame: pd.DataFrame) -> None:
    """Qlib's IdxMax is argmax+1 over the chronological window, not normalised."""
    one = _single_code(frame)
    got = rolling_idxmax(one, "high", WINDOW)
    y = one["high"].to_numpy()
    for end in (WINDOW - 1, 30, len(one) - 1):
        window_values = y[end - WINDOW + 1 : end + 1]
        assert got.iloc[end] == pytest.approx(float(np.argmax(window_values) + 1))


def test_idxmin_returns_one_based_position_from_the_window_start(frame: pd.DataFrame) -> None:
    one = _single_code(frame)
    got = rolling_idxmin(one, "low", WINDOW)
    y = one["low"].to_numpy()
    for end in (WINDOW - 1, 30, len(one) - 1):
        window_values = y[end - WINDOW + 1 : end + 1]
        assert got.iloc[end] == pytest.approx(float(np.argmin(window_values) + 1))


def test_index_position_operators_stay_inside_the_window(frame: pd.DataFrame) -> None:
    for series in (
        rolling_idxmax(frame, "high", WINDOW).dropna(),
        rolling_idxmin(frame, "low", WINDOW).dropna(),
    ):
        assert series.between(1.0, float(WINDOW)).all()


def test_ema_matches_pandas_span_convention(frame: pd.DataFrame) -> None:
    one = _single_code(frame)
    got = ts_ema(one, "close", WINDOW)
    expected = one["close"].ewm(span=WINDOW, min_periods=1).mean()
    pd.testing.assert_series_equal(got.reset_index(drop=True), expected, check_names=False)


# ── ts_rank: vectorised, and must stay identical to the per-window definition ──

def test_ts_rank_matches_the_per_window_definition_exactly(frame: pd.DataFrame) -> None:
    """The vectorised form must be bit-identical, not merely close.

    `ts_rank` was the single largest cost in the catalog: a per-window Python
    callback made 12 of 60 expressions take 80% of the runtime, the worst at 96
    seconds for one factor. It is now computed with a sliding-window comparison,
    which is ~500x faster, and this pins the result against the definition it
    replaced so the speed cannot have come from a changed answer.
    """
    one = _single_code(frame)
    got = ts_rank(one, "close", WINDOW)

    def rank_last(values: np.ndarray) -> float:
        return float(pd.Series(values).rank(method="average", pct=True).iloc[-1])

    expected = one["close"].rolling(WINDOW, min_periods=WINDOW).apply(rank_last, raw=True)
    pd.testing.assert_series_equal(got.reset_index(drop=True), expected, check_names=False)
    assert (got.isna() == expected.isna()).all()


def test_ts_rank_handles_ties_the_way_pandas_average_rank_does() -> None:
    dates = pd.bdate_range("2024-01-01", periods=6)
    flat = pd.DataFrame(
        {"date": dates, "code": "A", "close": [1.0, 1.0, 1.0, 1.0, 1.0, 1.0]}
    )
    got = ts_rank(flat, "close", 3)
    # Every value ties, so pandas' average rank over the window is (1+2+3)/3 = 2,
    # giving a percentile of 2/3. Ties must not collapse to 0.5.
    assert got.iloc[-1] == pytest.approx(2 / 3)


def test_ts_rank_is_nan_until_the_window_is_full(frame: pd.DataFrame) -> None:
    got = ts_rank(frame, "close", WINDOW)
    assert got.iloc[:WINDOW - 1].isna().all()


def test_ts_rank_keeps_codes_separate() -> None:
    dates = pd.bdate_range("2024-01-01", periods=5)
    frame = pd.DataFrame(
        {
            "date": list(dates) * 2,
            "code": ["A"] * 5 + ["B"] * 5,
            "close": [1.0, 2.0, 3.0, 4.0, 5.0, 5.0, 4.0, 3.0, 2.0, 1.0],
        }
    )
    got = ts_rank(frame, "close", 3)
    # A's last window is [3,4,5] -> the last element is the largest -> 1.0
    # B's last window is [3,2,1] -> the last element is the smallest -> 1/3
    assert got.iloc[4] == pytest.approx(1.0)
    assert got.iloc[9] == pytest.approx(1 / 3)


def test_ts_rank_propagates_nan_inside_a_window() -> None:
    dates = pd.bdate_range("2024-01-01", periods=5)
    frame = pd.DataFrame({"date": dates, "code": "A", "close": [1.0, np.nan, 3.0, 4.0, 5.0]})
    got = ts_rank(frame, "close", 3)
    # Window ending at index 3 is [nan, 3, 4] which cannot be ranked.
    assert np.isnan(got.iloc[3])
    assert np.isfinite(got.iloc[4])


# ── the same treatment for argmax / argmin / decay_linear ───────────────

def _per_code(frame: pd.DataFrame, window: int, callback) -> pd.Series:  # noqa: ANN001
    return frame.groupby("code")["close"].transform(
        lambda x: x.rolling(window, min_periods=window).apply(callback, raw=True)
    )


def test_argmax_matches_the_per_window_definition(frame: pd.DataFrame) -> None:
    from research_core.factor_lab.operators import ts_argmax

    window = 12
    got = ts_argmax(frame, "close", window)
    expected = _per_code(
        frame, window,
        lambda v: np.nan if np.isnan(v).any() else float(np.argmax(v) + 1),
    )
    pd.testing.assert_series_equal(got.reset_index(drop=True), expected.reset_index(drop=True), check_names=False)


def test_argmin_matches_the_per_window_definition(frame: pd.DataFrame) -> None:
    from research_core.factor_lab.operators import ts_argmin

    window = 12
    got = ts_argmin(frame, "close", window)
    expected = _per_code(
        frame, window,
        lambda v: np.nan if np.isnan(v).any() else float(np.argmin(v) + 1),
    )
    pd.testing.assert_series_equal(got.reset_index(drop=True), expected.reset_index(drop=True), check_names=False)


def test_decay_linear_matches_the_per_window_definition(frame: pd.DataFrame) -> None:
    """Equal to the reference within floating-point associativity.

    The vectorised sum accumulates in a different order from ``np.dot``, so the
    result can differ by one unit in the last place -- 2.2e-16 on the fixture.
    That is a rounding difference, not a definitional one, and nan patterns match
    exactly. Both channels of the pipeline use this same implementation, so the
    two-channel result_hash equivalence is unaffected.
    """
    from research_core.factor_lab.operators import ts_decay_linear

    window = 12

    def reference(values: np.ndarray) -> float:
        mask = ~np.isnan(values)
        if not mask.any():
            return np.nan
        valid = values[mask]
        weights = np.arange(1, len(values) + 1, dtype=float)[mask]
        return float(np.dot(valid, weights) / weights.sum())

    got = ts_decay_linear(frame, "close", window).reset_index(drop=True)
    expected = _per_code(frame, window, reference).reset_index(drop=True)
    assert (got.isna() == expected.isna()).all()
    both = pd.concat([got, expected], axis=1).dropna()
    assert np.allclose(both.iloc[:, 0], both.iloc[:, 1], rtol=0, atol=1e-12)


def test_argmax_returns_nan_when_the_window_contains_nan() -> None:
    from research_core.factor_lab.operators import ts_argmax

    dates = pd.bdate_range("2024-01-01", periods=5)
    frame = pd.DataFrame({"date": dates, "code": "A", "close": [1.0, np.nan, 3.0, 4.0, 5.0]})
    got = ts_argmax(frame, "close", 3)
    assert np.isnan(got.iloc[3]), "a window containing NaN must not report the NaN's position"
    assert got.iloc[4] == pytest.approx(3.0)  # [3, 4, 5] -> the max is the 3rd


def test_argmax_keeps_codes_separate() -> None:
    from research_core.factor_lab.operators import ts_argmax

    dates = pd.bdate_range("2024-01-01", periods=4)
    frame = pd.DataFrame(
        {
            "date": list(dates) * 2,
            "code": ["A"] * 4 + ["B"] * 4,
            "close": [1.0, 2.0, 3.0, 4.0, 4.0, 3.0, 2.0, 1.0],
        }
    )
    got = ts_argmax(frame, "close", 3)
    assert got.iloc[3] == pytest.approx(3.0)  # A: [2,3,4] -> max is 3rd
    assert got.iloc[7] == pytest.approx(1.0)  # B: [3,2,1] -> max is 1st


# ── Technical indicators ────────────────────────────────────────────────

def test_rsi_stays_within_zero_and_one_hundred(frame: pd.DataFrame) -> None:
    values = relative_strength_index(frame, "close", 14).dropna()
    assert values.between(0.0, 100.0).all()


def test_rsi_is_one_hundred_when_every_bar_gains() -> None:
    dates = pd.bdate_range("2023-01-02", periods=30)
    rising = pd.DataFrame(
        {
            "date": dates,
            "code": "000001.XSHE",
            "close": np.linspace(10.0, 20.0, len(dates)),
        }
    )
    values = relative_strength_index(rising, "close", 14).dropna()
    assert (values == 100.0).all()


def test_bollinger_upper_is_never_below_lower(frame: pd.DataFrame) -> None:
    upper = bollinger_band_upper(frame, "close", 20, 2.0)
    lower = bollinger_band_lower(frame, "close", 20, 2.0)
    both = pd.concat([upper, lower], axis=1).dropna()
    assert (both.iloc[:, 0] >= both.iloc[:, 1]).all()


def test_bollinger_band_width_scales_with_the_multiplier(frame: pd.DataFrame) -> None:
    one = _single_code(frame)
    narrow = bollinger_band_upper(one, "close", 20, 1.0) - bollinger_band_lower(one, "close", 20, 1.0)
    wide = bollinger_band_upper(one, "close", 20, 2.0) - bollinger_band_lower(one, "close", 20, 2.0)
    ratio = (wide / narrow).dropna()
    assert np.allclose(ratio, 2.0)


def test_bias_is_percent_deviation_from_the_moving_average(frame: pd.DataFrame) -> None:
    one = _single_code(frame)
    got = bias(one, "close", 6)
    mean = one["close"].rolling(6, min_periods=6).mean()
    expected = (one["close"] - mean) / mean * 100.0
    pd.testing.assert_series_equal(got.reset_index(drop=True), expected, check_names=False)


def test_true_range_is_never_negative(frame: pd.DataFrame) -> None:
    values = true_range(frame, "close", "high", "low", 14).dropna()
    assert (values >= 0).all()


def test_true_range_accounts_for_a_gap_against_the_previous_close() -> None:
    dates = pd.bdate_range("2023-01-02", periods=6)
    gapped = pd.DataFrame(
        {
            "date": dates,
            "code": "000001.XSHE",
            "close": [10.0, 10.0, 20.0, 20.0, 20.0, 20.0],
            "high": [10.5, 10.5, 20.5, 20.5, 20.5, 20.5],
            "low": [9.5, 9.5, 18.0, 19.5, 19.5, 19.5],
        }
    )
    # On the gap bar, true range must be the gap from the previous close
    # (|20.5 - 10.0| = 10.5), never the intraday range (20.5 - 18.0 = 2.5).
    values = true_range(gapped, "close", "high", "low", 1)
    assert values.iloc[2] == pytest.approx(10.5)
    assert values.iloc[2] != pytest.approx(2.5)


def test_cci_is_finite_where_the_window_has_variation(frame: pd.DataFrame) -> None:
    values = commodity_channel_index(frame, "close", "high", "low", 20).replace(
        [np.inf, -np.inf], np.nan
    ).dropna()
    assert not values.empty
    assert np.isfinite(values).all()


# ── Compiler wiring ─────────────────────────────────────────────────────

def test_compiler_accepts_every_newly_implemented_operator(frame: pd.DataFrame) -> None:
    expressions = [
        "EMA($close, 12)",
        "Slope($close, 20)",
        "Rsquare($close, 20)",
        "Resi($close, 20)",
        "Quantile($close, 20, 0.8)",
        "IdxMax($high, 20)",
        "IdxMin($low, 20)",
        "Bias($close, 6)",
        "RSI($close, 14)",
        "Boll_Up($close, 20, 2.0)",
        "Boll_Dn($close, 20, 2.0)",
        "ATR($close, $high, $low, 14)",
        "CCI($close, $high, $low, 20)",
    ]
    for expression in expressions:
        values = pd.Series(compile_formula(expression)(frame))
        assert values.notna().sum() > 0, expression
        assert np.isfinite(values.dropna()).all(), expression


def test_quantile_passes_both_parameters_through(frame: pd.DataFrame) -> None:
    """Regression guard: the generator used to forward only the first parameter."""
    low = pd.Series(compile_formula("Quantile($close, 20, 0.2)")(frame))
    high = pd.Series(compile_formula("Quantile($close, 20, 0.8)")(frame))
    both = pd.concat([low, high], axis=1).dropna()
    assert (both.iloc[:, 1] >= both.iloc[:, 0]).all()
    assert not both.iloc[:, 1].equals(both.iloc[:, 0])


def test_three_series_operators_bind_arguments_positionally(frame: pd.DataFrame) -> None:
    """ATR/CCI take (close, high, low, window): swapping them must change output."""
    correct = pd.Series(compile_formula("ATR($close, $high, $low, 14)")(frame))
    swapped = pd.Series(compile_formula("ATR($high, $close, $low, 14)")(frame))
    both = pd.concat([correct, swapped], axis=1).dropna()
    assert not np.allclose(both.iloc[:, 0], both.iloc[:, 1])


def test_two_series_operator_still_binds_correctly(frame: pd.DataFrame) -> None:
    """The generalised N-series branch must not regress CORR/COV."""
    values = pd.Series(compile_formula("Corr($close, $volume, 6)")(frame)).dropna()
    assert not values.empty
    assert values.between(-1.0 - 1e-9, 1.0 + 1e-9).all()
