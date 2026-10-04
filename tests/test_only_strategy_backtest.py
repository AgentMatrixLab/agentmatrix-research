"""TEST-ONLY tests for the weight-based strategy backtest.

Prices here are synthetic. These tests pin the *accounting* -- how weights become
holdings, how turnover becomes cost, how the NAV evolves -- because that is where
a backtest most easily flatters itself. They say nothing about any strategy's
return.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research_core.strategy_operations.strategy_backtest import (
    BacktestError,
    backtest_weights,
    curve_from_nav,
    summarise_curve,
)

DATES = pd.bdate_range("2024-01-01", periods=26)


def prices_frame(levels: dict[str, list[float]] | None = None) -> pd.DataFrame:
    levels = levels or {"A": [100.0] * len(DATES), "B": [50.0] * len(DATES)}
    rows = []
    for code, series in levels.items():
        for date, price in zip(DATES, series):
            rows.append({"date": date, "code": code, "close": price})
    return pd.DataFrame(rows)


def weights_frame(entries: list[tuple[str, str, float]]) -> pd.DataFrame:
    return pd.DataFrame(
        [{"date": pd.Timestamp(d), "code": c, "weight": w} for d, c, w in entries]
    )


# ── accounting basics ───────────────────────────────────────────────────

def test_a_single_buy_and_hold_tracks_the_price() -> None:
    """Buy A at 100, hold while it rises to 110: NAV must rise by 10% less cost."""
    levels = {"A": [100.0 + i for i in range(len(DATES))]}  # 100 -> 125
    result = backtest_weights(
        weights_frame([(DATES[0], "A", 1.0)]),
        prices_frame(levels),
        round_trip_cost=0.0,
    )
    first, last = result["curve"][0], result["curve"][-1]
    assert first["nav"] == pytest.approx(1.0)
    assert last["nav"] == pytest.approx(125.0 / 100.0)


def test_the_first_rebalance_pays_a_full_turnover_cost() -> None:
    """Buying from cash trades the whole portfolio, not a delta against nothing."""
    result = backtest_weights(
        weights_frame([(DATES[0], "A", 1.0)]),
        prices_frame({"A": [100.0] * len(DATES)}),
        round_trip_cost=0.003,
    )
    assert result["rebalances"][0]["traded_fraction"] == pytest.approx(1.0)
    assert result["rebalances"][0]["cost"] == pytest.approx(0.003)
    assert result["curve"][0]["nav"] == pytest.approx(0.997)


def test_no_trade_means_no_cost() -> None:
    """A second rebalance to the identical weights must cost nothing."""
    flat = {"A": [100.0] * len(DATES)}
    result = backtest_weights(
        weights_frame([(DATES[0], "A", 1.0), (DATES[10], "A", 1.0)]),
        prices_frame(flat),
        round_trip_cost=0.003,
    )
    assert result["rebalances"][1]["traded_fraction"] == pytest.approx(0.0, abs=1e-12)
    assert result["rebalances"][1]["cost"] == pytest.approx(0.0, abs=1e-12)


def test_weights_drift_between_rebalances() -> None:
    """Holding shares means the weight drifts; re-imposing it daily is a free lunch.

    A is flat and B doubles. Holding B at 50% must end above 50% of the book, so
    the second rebalance has to sell B back down -- which costs money.
    """
    a = [100.0] * len(DATES)
    b = [50.0 * (2 ** (i / (len(DATES) - 1))) for i in range(len(DATES))]
    result = backtest_weights(
        weights_frame([(DATES[0], "A", 0.5), (DATES[0], "B", 0.5), (DATES[-1], "A", 0.5), (DATES[-1], "B", 0.5)]),
        prices_frame({"A": a, "B": b}),
        round_trip_cost=0.003,
    )
    # B doubled, so before the final rebalance it is 2/3 of the book, not 1/2.
    final_trade = result["rebalances"][-1]["traded_fraction"]
    assert final_trade == pytest.approx(1 / 6, abs=0.02)


def test_turnover_is_half_the_gross_traded_notional() -> None:
    """Replacing half the book costs half a round trip, not a whole one."""
    flat = {"A": [100.0] * len(DATES), "B": [100.0] * len(DATES)}
    result = backtest_weights(
        weights_frame([(DATES[0], "A", 1.0), (DATES[10], "B", 1.0)]),
        prices_frame(flat),
        round_trip_cost=0.003,
    )
    # Sell all of A (weight 1) and buy all of B (weight 1): sum|dw| = 2, /2 = 1.
    assert result["rebalances"][1]["traded_fraction"] == pytest.approx(1.0)


def test_a_partial_rotation_costs_proportionally() -> None:
    flat = {"A": [100.0] * len(DATES), "B": [100.0] * len(DATES), "C": [100.0] * len(DATES)}
    result = backtest_weights(
        weights_frame(
            [(DATES[0], "A", 0.5), (DATES[0], "B", 0.5), (DATES[10], "C", 0.5), (DATES[10], "B", 0.5)]
        ),
        prices_frame(flat),
        round_trip_cost=0.003,
    )
    # Sell 0.5 of A, buy 0.5 of C: sum|dw| = 1.0, /2 = 0.5.
    assert result["rebalances"][1]["traded_fraction"] == pytest.approx(0.5)


def test_cost_reduces_nav_by_turnover_times_round_trip() -> None:
    flat = {"A": [100.0] * len(DATES)}
    result = backtest_weights(
        weights_frame([(DATES[0], "A", 1.0)]),
        prices_frame(flat),
        round_trip_cost=0.01,
    )
    assert result["curve"][-1]["nav"] == pytest.approx(0.99)


# ── guard rails ─────────────────────────────────────────────────────────

def test_levered_targets_are_refused() -> None:
    with pytest.raises(BacktestError, match="levered"):
        backtest_weights(
            weights_frame([(DATES[0], "A", 0.8), (DATES[0], "B", 0.8)]),
            prices_frame(),
        )


def test_a_missing_rebalance_date_snaps_forward() -> None:
    """A signal dated on a holiday trades at the next available close."""
    holiday = pd.Timestamp("2024-01-06")  # a Saturday
    result = backtest_weights(
        weights_frame([(holiday, "A", 1.0)]),
        prices_frame({"A": [100.0] * len(DATES)}),
    )
    assert result["rebalances"][0]["date"] >= holiday


def test_invalid_parameters_are_refused() -> None:
    with pytest.raises(BacktestError, match="initial_nav"):
        backtest_weights(weights_frame([(DATES[0], "A", 1.0)]), prices_frame(), initial_nav=0)
    with pytest.raises(BacktestError, match="round_trip_cost"):
        backtest_weights(weights_frame([(DATES[0], "A", 1.0)]), prices_frame(), round_trip_cost=-1)


def test_missing_columns_are_named() -> None:
    with pytest.raises(BacktestError, match="weights is missing"):
        backtest_weights(pd.DataFrame({"date": DATES}), prices_frame())
    with pytest.raises(BacktestError, match="prices is missing"):
        backtest_weights(weights_frame([(DATES[0], "A", 1.0)]), pd.DataFrame({"date": DATES}))


def test_empty_inputs_are_refused() -> None:
    with pytest.raises(BacktestError, match="weights are empty"):
        backtest_weights(pd.DataFrame(columns=["date", "code", "weight"]), prices_frame())
    with pytest.raises(BacktestError, match="prices are empty"):
        backtest_weights(
            weights_frame([(DATES[0], "A", 1.0)]), pd.DataFrame(columns=["date", "code", "close"])
        )


def test_a_held_name_losing_its_price_stops_the_backtest() -> None:
    """Neither zero nor a stale carry is safe, so the default is to stop.

    Zeroing an unquoted holding vaporises the position; carrying the last close
    hides a delisting behind a flat line. The caller has to choose.
    """
    rows = [{"date": d, "code": "A", "close": 100.0} for d in DATES]
    rows += [{"date": d, "code": "B", "close": 100.0} for d in DATES[:10]]
    prices = pd.DataFrame(rows)
    with pytest.raises(BacktestError, match="no price on"):
        backtest_weights(
            weights_frame([(DATES[0], "A", 0.5), (DATES[0], "B", 0.5)]),
            prices,
            round_trip_cost=0.0,
        )


def test_carrying_the_last_close_is_available_but_explicit() -> None:
    rows = [{"date": d, "code": "A", "close": 100.0} for d in DATES]
    rows += [{"date": d, "code": "B", "close": 100.0} for d in DATES[:10]]
    prices = pd.DataFrame(rows)
    result = backtest_weights(
        weights_frame([(DATES[0], "A", 0.5), (DATES[0], "B", 0.5)]),
        prices,
        round_trip_cost=0.0,
        missing_price_policy="last_close",
    )
    # B is carried at its last close of 100, so the book stays at 1.0.
    assert result["curve"][-1]["nav"] == pytest.approx(1.0)
    assert all(np.isfinite(point["nav"]) for point in result["curve"])


def test_an_unknown_missing_price_policy_is_refused() -> None:
    with pytest.raises(BacktestError, match="missing_price_policy"):
        backtest_weights(
            weights_frame([(DATES[0], "A", 1.0)]),
            prices_frame({"A": [100.0] * len(DATES)}),
            missing_price_policy="ignore",
        )


def test_curve_is_finite_and_dates_are_iso() -> None:
    result = backtest_weights(
        weights_frame([(DATES[0], "A", 1.0)]),
        prices_frame({"A": [100.0 + i for i in range(len(DATES))]}),
    )
    for point in result["curve"]:
        assert np.isfinite(point["nav"])
        assert len(point["date"]) == 10 and point["date"][4] == "-"


# ── benchmark alignment ─────────────────────────────────────────────────

def test_benchmark_is_normalised_to_one_at_the_start() -> None:
    bench = pd.Series({date: 3000.0 + i for i, date in enumerate(DATES)})
    result = backtest_weights(
        weights_frame([(DATES[0], "A", 1.0)]),
        prices_frame({"A": [100.0] * len(DATES)}),
        benchmark=bench,
        round_trip_cost=0.0,
    )
    assert result["curve"][0]["benchmark"] == pytest.approx(1.0)
    assert result["curve"][-1]["benchmark"] == pytest.approx((3000.0 + len(DATES) - 1) / 3000.0)


def test_no_benchmark_leaves_the_field_empty() -> None:
    result = backtest_weights(
        weights_frame([(DATES[0], "A", 1.0)]), prices_frame({"A": [100.0] * len(DATES)})
    )
    assert all(point["benchmark"] is None for point in result["curve"])


# ── diagnostics and integration with the existing analytics ─────────────

def test_diagnostics_report_turnover_and_cost() -> None:
    result = backtest_weights(
        weights_frame([(DATES[0], "A", 1.0)]),
        prices_frame({"A": [100.0] * len(DATES)}),
        round_trip_cost=0.003,
    )
    metrics = result["metrics"]
    assert metrics["rebalances"] == 1
    assert metrics["total_traded_fraction"] == pytest.approx(1.0)
    assert metrics["total_cost_fraction"] == pytest.approx(0.003)
    assert metrics["final_nav"] == pytest.approx(result["curve"][-1]["nav"])
    assert "one-sided" in result["turnover_basis"]


def test_curve_feeds_the_existing_analytics_module() -> None:
    """The whole point: produce a curve `analyze_window` accepts."""
    bench = pd.Series({date: 100.0 + i for i, date in enumerate(DATES)})
    result = backtest_weights(
        weights_frame([(DATES[0], "A", 1.0)]),
        prices_frame({"A": [100.0 + 2 * i for i in range(len(DATES))]}),
        benchmark=bench,
    )
    metrics = summarise_curve(result["curve"])
    assert metrics["observations"] == len(DATES)
    assert metrics["total_return"] > 0
    assert metrics["excess_return"] is not None
    assert metrics["start"] < metrics["end"]
    assert 0.0 <= metrics["win_rate"] <= 1.0


def test_curve_from_nav_normalises_the_benchmark() -> None:
    nav = {"2024-01-01": 1.0, "2024-01-02": 1.1}
    bench = {"2024-01-01": 2000.0, "2024-01-02": 2100.0}
    curve = curve_from_nav(nav, benchmark=bench)
    assert curve[0]["benchmark"] == pytest.approx(1.0)
    assert curve[1]["benchmark"] == pytest.approx(1.05)


def test_summarise_refuses_a_degenerate_curve() -> None:
    with pytest.raises(BacktestError, match="at least two"):
        summarise_curve([{"date": "2024-01-01", "nav": 1.0}])
