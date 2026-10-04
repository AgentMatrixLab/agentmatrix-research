"""TEST-ONLY tests for signal generation, order export and reconciliation.

Prices and holdings here are synthetic. These tests pin the *rules* -- lot
rounding, cap redistribution, export format, deviation verdicts -- and say
nothing about any strategy's profitability.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pandas as pd
import pytest

from research_core.strategy_operations.signal_pipeline import (
    LOT_SIZE,
    Order,
    SignalError,
    build_targets,
    diff_positions,
    reconcile_execution,
    to_conditional_orders,
    to_supabase_rows,
    write_conditional_orders,
    write_file_orders,
)

PRICES = {f"S{i:03d}": 10.0 + i for i in range(60)}
SCORES = {f"S{i:03d}": 100.0 - i for i in range(60)}


# ── stage 1: targets ────────────────────────────────────────────────────

def test_targets_are_whole_lots() -> None:
    positions = build_targets(SCORES, total_value=1e7, prices=PRICES, top_n=20)
    assert positions
    for position in positions:
        assert position.shares % LOT_SIZE == 0
        assert position.shares > 0


def test_targets_pick_the_highest_scores() -> None:
    positions = build_targets(SCORES, total_value=1e7, prices=PRICES, top_n=5)
    assert [p.code for p in positions] == ["S000", "S001", "S002", "S003", "S004"]


def test_equal_weighting_is_near_equal_before_caps() -> None:
    positions = build_targets(
        SCORES, total_value=1e8, prices=PRICES, top_n=20, max_weight=0.5
    )
    weights = [p.weight for p in positions]
    assert max(weights) - min(weights) < 1e-9


def test_weights_respect_the_cap() -> None:
    positions = build_targets(
        SCORES, total_value=1e7, prices=PRICES, top_n=10, max_weight=0.12
    )
    assert all(p.weight <= 0.12 + 1e-9 for p in positions)


def test_capped_excess_is_redistributed_not_discarded() -> None:
    positions = build_targets(
        SCORES, total_value=1e8, prices=PRICES, top_n=10, max_weight=0.12
    )
    # 10 names at 12% would total 120%; redistribution must still spend ~100%.
    assert sum(p.weight for p in positions) == pytest.approx(1.0, abs=1e-6)


def test_score_weighting_is_monotone_in_the_score() -> None:
    positions = build_targets(
        SCORES, total_value=1e8, prices=PRICES, top_n=10, weighting="score", max_weight=0.9
    )
    weights = [p.weight for p in positions]
    assert weights == sorted(weights, reverse=True)


def test_a_name_too_small_for_one_lot_is_dropped_not_rounded_up() -> None:
    """Rounding up would over-order; dropping is the conservative choice."""
    scores = {"BIG": 10.0, "TINY": 9.0}
    prices = {"BIG": 10.0, "TINY": 1000.0}
    # 10,000 split 50/50: BIG buys 5 lots, TINY's 5,000 is under one 1000-price
    # lot (100,000), so TINY must be dropped rather than rounded up.
    positions = build_targets(
        scores, total_value=10_000.0, prices=prices, top_n=2, max_weight=0.5
    )
    assert [p.code for p in positions] == ["BIG"]


def test_targets_raise_when_nothing_is_affordable() -> None:
    with pytest.raises(SignalError, match="below one lot"):
        build_targets(
            {"A": 1.0}, total_value=50.0, prices={"A": 1000.0}, top_n=1, max_weight=1.0
        )


def test_targets_skip_codes_without_a_usable_price() -> None:
    scores = {"A": 3.0, "B": 2.0, "C": 1.0}
    prices = {"A": 10.0, "C": 10.0}
    positions = build_targets(scores, total_value=1e6, prices=prices, top_n=3)
    assert {p.code for p in positions} == {"A", "C"}


def test_targets_reject_an_empty_score_set() -> None:
    with pytest.raises(SignalError, match="no scores"):
        build_targets({}, total_value=1e6, prices=PRICES)


def test_targets_reject_invalid_parameters() -> None:
    with pytest.raises(SignalError, match="total_value"):
        build_targets(SCORES, total_value=0, prices=PRICES)
    with pytest.raises(SignalError, match="top_n"):
        build_targets(SCORES, total_value=1e6, prices=PRICES, top_n=0)
    with pytest.raises(SignalError, match="max_weight"):
        build_targets(SCORES, total_value=1e6, prices=PRICES, max_weight=0.0)
    with pytest.raises(SignalError, match="weighting"):
        build_targets(SCORES, total_value=1e6, prices=PRICES, weighting="magic")


def test_targets_are_deterministic_on_ties() -> None:
    tied = {"B": 1.0, "A": 1.0, "C": 1.0}
    prices = {"A": 10.0, "B": 10.0, "C": 10.0}
    first = build_targets(tied, total_value=1e6, prices=prices, top_n=3)
    second = build_targets(tied, total_value=1e6, prices=prices, top_n=3)
    assert [p.code for p in first] == [p.code for p in second]


# ── stage 2: orders ─────────────────────────────────────────────────────

def test_orders_buy_into_a_new_basket() -> None:
    targets = build_targets(SCORES, total_value=1e7, prices=PRICES, top_n=5)
    orders = diff_positions(targets, {}, total_value=1e7)
    assert orders and all(order.side == "buy" for order in orders)
    assert {order.code for order in orders} == {p.code for p in targets}


def test_orders_are_empty_when_holdings_already_match() -> None:
    targets = build_targets(SCORES, total_value=1e7, prices=PRICES, top_n=5)
    holdings = {p.code: p.shares for p in targets}
    assert diff_positions(targets, holdings, total_value=1e7) == []


def test_names_leaving_the_basket_are_sold_in_full() -> None:
    targets = build_targets(SCORES, total_value=1e7, prices=PRICES, top_n=3)
    holdings = {"S099": 500, "S000": 100}
    orders = diff_positions(
        targets, holdings, total_value=1e7, prices={"S099": 20.0}
    )
    exit_order = next(order for order in orders if order.code == "S099")
    assert exit_order.side == "sell"
    assert exit_order.shares == 500
    assert exit_order.reason == "exit_not_in_target"


def test_order_quantity_is_the_delta_not_the_target() -> None:
    targets = build_targets(SCORES, total_value=1e7, prices=PRICES, top_n=3)
    held = targets[0].shares // 2
    orders = diff_positions(targets, {targets[0].code: held}, total_value=1e7)
    order = next(o for o in orders if o.code == targets[0].code)
    assert order.shares == targets[0].shares - held


def test_sells_are_emitted_before_buys() -> None:
    """Freeing cash first is what makes the basket affordable."""
    targets = build_targets(SCORES, total_value=1e7, prices=PRICES, top_n=3)
    orders = diff_positions(
        targets, {"S099": 1000}, total_value=1e7, prices={"S099": 20.0}
    )
    assert orders[0].side == "sell"


def test_refuses_to_sell_a_holding_with_no_price() -> None:
    """An unknown sale price is a real-money error, not something to guess."""
    targets = build_targets(SCORES, total_value=1e7, prices=PRICES, top_n=2)
    with pytest.raises(SignalError, match="no usable price"):
        diff_positions(targets, {"GHOST": 100}, total_value=1e7)


# ── stage 3: exports ────────────────────────────────────────────────────

def _orders() -> list[Order]:
    return [
        Order("S000", "buy", 1000, 10.0, 0.05, 0.0, "rebalance_to_target"),
        Order("S099", "sell", 500, 20.0, 0.0, 0.03, "exit_not_in_target"),
    ]


def test_file_order_csv_has_the_expected_header_and_rows(tmp_path: Path) -> None:
    path = write_file_orders(_orders(), tmp_path / "orders.csv")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 2
    assert rows[0]["code"] == "S000"
    assert rows[0]["side"] == "buy"
    assert rows[0]["shares"] == "1000"
    assert rows[0]["price_type"] == "limit"


def test_file_order_csv_is_written_bom_first_for_excel_and_qmt() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as folder:
        path = write_file_orders(_orders(), Path(folder) / "orders.csv")
        assert path.read_bytes().startswith(b"\xef\xbb\xbf")


def test_file_order_csv_carries_extra_template_columns(tmp_path: Path) -> None:
    path = write_file_orders(
        _orders(), tmp_path / "orders.csv", extra={"account": "A1", "strategy": "S"}
    )
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["account"] == "A1"
    assert rows[0]["strategy"] == "S"


def test_conditional_orders_carry_an_explicit_trigger_price() -> None:
    payload = to_conditional_orders(
        _orders(), strategy_id="strat", trade_date="2026-10-06", price_offset_bps=50.0
    )
    buy = next(item for item in payload if item["side"] == "buy")
    sell = next(item for item in payload if item["side"] == "sell")
    assert buy["trigger_price"] == pytest.approx(10.0 * (1 - 0.005))
    assert sell["trigger_price"] == pytest.approx(20.0 * (1 + 0.005))


def test_conditional_order_file_is_valid_json(tmp_path: Path) -> None:
    path = write_conditional_orders(
        _orders(), tmp_path / "cond.json", strategy_id="strat", trade_date="2026-10-06"
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["strategy_id"] == "strat"
    assert len(payload["orders"]) == 2
    assert payload["generated_at"]


def test_supabase_rows_are_idempotent_by_batch_key() -> None:
    rows = to_supabase_rows(
        _orders(), strategy_id="strat", trade_date="2026-10-06", portfolio_value=1e7
    )
    assert all(row["strategy_id"] == "strat" for row in rows)
    assert all(row["trade_date"] == "2026-10-06" for row in rows)
    assert all(row["signal_batch"] == "strat-2026-10-06" for row in rows)
    assert all(row["status"] == "pending" for row in rows)
    codes = [row["code"] for row in rows]
    assert len(codes) == len(set(codes)), "one row per code keeps the upsert idempotent"


# ── stage 4: reconciliation ─────────────────────────────────────────────

def _fills(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_a_perfect_fill_reconciles_clean() -> None:
    report = reconcile_execution(
        _orders(),
        _fills(
            [
                {"code": "S000", "side": "buy", "shares": 1000, "price": 10.0},
                {"code": "S099", "side": "sell", "shares": 500, "price": 20.0},
            ]
        ),
        trade_date="2026-10-06",
        strategy_id="strat",
    )
    assert report.is_clean
    assert report.matched == 2
    assert report.fill_ratio == pytest.approx(1.0)
    assert report.missing == []


def test_an_unfilled_order_is_reported_missing() -> None:
    report = reconcile_execution(
        _orders(),
        _fills([{"code": "S000", "side": "buy", "shares": 1000, "price": 10.0}]),
        trade_date="2026-10-06",
        strategy_id="strat",
    )
    assert not report.is_clean
    assert [row["code"] for row in report.missing] == ["S099"]


def test_a_partial_fill_is_a_quantity_break_by_default() -> None:
    """A half-filled basket is a different portfolio from the validated one."""
    report = reconcile_execution(
        _orders(),
        _fills(
            [
                {"code": "S000", "side": "buy", "shares": 600, "price": 10.0},
                {"code": "S099", "side": "sell", "shares": 500, "price": 20.0},
            ]
        ),
        trade_date="2026-10-06",
        strategy_id="strat",
    )
    assert [row["code"] for row in report.quantity_breaks] == ["S000"]
    assert report.quantity_breaks[0]["delta"] == -400


def test_a_partial_fill_within_tolerance_is_accepted() -> None:
    report = reconcile_execution(
        _orders(),
        _fills(
            [
                {"code": "S000", "side": "buy", "shares": 990, "price": 10.0},
                {"code": "S099", "side": "sell", "shares": 500, "price": 20.0},
            ]
        ),
        trade_date="2026-10-06",
        strategy_id="strat",
        quantity_tolerance=0.02,
    )
    assert report.is_clean


def test_an_unexpected_fill_is_reported() -> None:
    report = reconcile_execution(
        _orders(),
        _fills(
            [
                {"code": "S000", "side": "buy", "shares": 1000, "price": 10.0},
                {"code": "S099", "side": "sell", "shares": 500, "price": 20.0},
                {"code": "MYSTERY", "side": "buy", "shares": 100, "price": 5.0},
            ]
        ),
        trade_date="2026-10-06",
        strategy_id="strat",
    )
    assert [row["code"] for row in report.unexpected] == ["MYSTERY"]
    assert not report.is_clean


def test_slippage_is_positive_when_adverse_for_both_directions() -> None:
    """Implementation shortfall: positive always means worse, either side."""
    report = reconcile_execution(
        _orders(),
        _fills(
            [
                {"code": "S000", "side": "buy", "shares": 1000, "price": 10.5},
                {"code": "S099", "side": "sell", "shares": 500, "price": 19.0},
            ]
        ),
        trade_date="2026-10-06",
        strategy_id="strat",
        slippage_warn_bps=20.0,
    )
    by_code = {row["code"]: row["slippage_bps"] for row in report.price_slippage}
    # Bought above reference: adverse.
    assert by_code["S000"] == pytest.approx(500.0)
    # Sold below reference: also adverse, also positive.
    assert by_code["S099"] == pytest.approx(500.0)


def test_slippage_is_negative_when_favourable() -> None:
    report = reconcile_execution(
        _orders(),
        _fills(
            [
                {"code": "S000", "side": "buy", "shares": 1000, "price": 9.5},
                {"code": "S099", "side": "sell", "shares": 500, "price": 21.0},
            ]
        ),
        trade_date="2026-10-06",
        strategy_id="strat",
        slippage_warn_bps=20.0,
    )
    by_code = {row["code"]: row["slippage_bps"] for row in report.price_slippage}
    assert by_code["S000"] == pytest.approx(-500.0)
    assert by_code["S099"] == pytest.approx(-500.0)


def test_slippage_is_ranked_worst_first() -> None:
    report = reconcile_execution(
        _orders(),
        _fills(
            [
                {"code": "S000", "side": "buy", "shares": 1000, "price": 10.5},
                {"code": "S099", "side": "sell", "shares": 500, "price": 20.8},
            ]
        ),
        trade_date="2026-10-06",
        strategy_id="strat",
        slippage_warn_bps=10.0,
    )
    magnitudes = [abs(row["slippage_bps"]) for row in report.price_slippage]
    assert magnitudes == sorted(magnitudes, reverse=True)


def test_small_slippage_is_not_reported() -> None:
    report = reconcile_execution(
        _orders(),
        _fills(
            [
                {"code": "S000", "side": "buy", "shares": 1000, "price": 10.01},
                {"code": "S099", "side": "sell", "shares": 500, "price": 20.0},
            ]
        ),
        trade_date="2026-10-06",
        strategy_id="strat",
        slippage_warn_bps=20.0,
    )
    assert report.price_slippage == []


def test_fill_ratio_uses_notional_not_counts() -> None:
    report = reconcile_execution(
        _orders(),
        _fills([{"code": "S000", "side": "buy", "shares": 1000, "price": 10.0}]),
        trade_date="2026-10-06",
        strategy_id="strat",
    )
    assert report.intended_notional == pytest.approx(1000 * 10.0 + 500 * 20.0)
    assert report.filled_notional == pytest.approx(1000 * 10.0)
    assert report.fill_ratio == pytest.approx(10000.0 / 20000.0)


def test_reconciliation_reports_missing_columns() -> None:
    with pytest.raises(SignalError, match="missing columns"):
        reconcile_execution(
            _orders(), pd.DataFrame({"code": ["S000"]}), trade_date="d", strategy_id="s"
        )


def test_markdown_report_states_the_verdict() -> None:
    clean = reconcile_execution(
        _orders(),
        _fills(
            [
                {"code": "S000", "side": "buy", "shares": 1000, "price": 10.0},
                {"code": "S099", "side": "sell", "shares": 500, "price": 20.0},
            ]
        ),
        trade_date="2026-10-06",
        strategy_id="strat",
    )
    assert "无偏差" in clean.render_markdown()

    dirty = reconcile_execution(
        _orders(), _fills([{"code": "S000", "side": "buy", "shares": 1000, "price": 10.0}]),
        trade_date="2026-10-06", strategy_id="strat",
    )
    text = dirty.render_markdown()
    assert "存在偏差" in text
    assert "未成交" in text


def test_report_dict_is_json_serialisable() -> None:
    report = reconcile_execution(
        _orders(), _fills([{"code": "S000", "side": "buy", "shares": 1000, "price": 10.0}]),
        trade_date="2026-10-06", strategy_id="strat",
    )
    json.dumps(report.as_dict())
