"""TEST-ONLY tests for the execution-deviation reconciliation.

The brief asks for live signals "供本地 QMT 或掘金量化对照执行偏差": the terminal executes, and
the deviation is measured against what was intended. The library could measure it
(`reconcile_execution`) but nothing called it, so this script is the other half. These tests
pin the three ways the comparison must behave: a faithful fill set is clean, every kind of
deviation is reported rather than smoothed over, and a malformed fills file is refused instead
of being scored as "everything missing".
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from reconcile_signals import ReconcileError, load_orders, main  # noqa: E402
from research_core.strategy_operations.signal_pipeline import write_file_orders  # noqa: E402

ORDER_ROWS = [
    ("600000.XSHG", "buy", 1000, 10.0, 0.02, "rebalance_to_target"),
    ("600001.XSHG", "buy", 500, 20.0, 0.02, "rebalance_to_target"),
    ("600002.XSHG", "sell", 300, 30.0, 0.0, "exit_not_in_target"),
]


def _orders_csv(root: Path) -> Path:
    from research_core.strategy_operations.signal_pipeline import Order

    orders = [
        Order(code=code, side=side, shares=shares, reference_price=price,
              target_weight=weight, current_weight=0.0, reason=reason)
        for code, side, shares, price, weight, reason in ORDER_ROWS
    ]
    path = root / "live_signals" / "file_orders.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    write_file_orders(orders, path)
    (path.parent / "signal_summary.json").write_text(
        json.dumps({"trade_date": "2026-08-31", "strategy_id": "chenxi_core_v1"}),
        encoding="utf-8",
    )
    return path


def _fills(root: Path, rows: list[tuple[str, int, float]]) -> Path:
    path = root / "fills.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["code", "shares", "price"])
        writer.writerows(rows)
    return path


def _run(root: Path, orders: Path, fills: Path, out: Path, *extra: str) -> int:
    return main([
        "--orders", str(orders), "--fills", str(fills), "--out-dir", str(out), *extra,
    ])


def test_only_round_trips_the_delivered_orders(tmp_path: Path) -> None:
    orders = load_orders(_orders_csv(tmp_path))
    assert [order.code for order in orders] == [row[0] for row in ORDER_ROWS]
    assert [order.shares for order in orders] == [row[2] for row in ORDER_ROWS]
    assert [order.reference_price for order in orders] == [row[3] for row in ORDER_ROWS]


def test_only_a_faithful_fill_set_is_clean(tmp_path: Path) -> None:
    root = tmp_path
    orders = _orders_csv(root)
    fills = _fills(root, [
        ("600000.XSHG", 1000, 10.02),
        ("600001.XSHG", 500, 19.98),
        ("600002.XSHG", 300, 30.01),
    ])
    out = root / "out"
    code = _run(root, orders, fills, out, "--slippage-warn-bps", "50")

    assert code == 0, "a faithful fill set must not be reported as a deviation"
    payload = json.loads((out / "deviation_report.json").read_text(encoding="utf-8"))
    assert payload["is_clean"] is True
    assert payload["trade_date"] == "2026-08-31"
    assert payload["missing"] == []
    assert payload["quantity_breaks"] == []
    markdown = (out / "deviation_report.md").read_text(encoding="utf-8")
    assert "无偏差" in markdown


def test_only_reports_every_kind_of_deviation(tmp_path: Path) -> None:
    root = tmp_path
    orders = _orders_csv(root)
    fills = _fills(root, [
        ("600000.XSHG", 400, 10.0),      # partial fill -> quantity break
        ("600003.XSHG", 100, 5.0),       # never intended -> unexpected
        ("600001.XSHG", 500, 25.0),      # 25% worse than the reference -> slippage
        # 600002.XSHG absent entirely  -> missing
    ])
    out = root / "out"
    code = _run(root, orders, fills, out, "--slippage-warn-bps", "20")

    assert code == 5, "deviations must be reported with a non-zero exit"
    payload = json.loads((out / "deviation_report.json").read_text(encoding="utf-8"))
    assert payload["is_clean"] is False
    assert [item["code"] for item in payload["missing"]] == ["600002.XSHG"]
    assert [item["code"] for item in payload["unexpected"]] == ["600003.XSHG"]
    assert [item["code"] for item in payload["quantity_breaks"]] == ["600000.XSHG"]
    assert [item["code"] for item in payload["price_slippage"]] == ["600001.XSHG"]
    markdown = (out / "deviation_report.md").read_text(encoding="utf-8")
    assert "存在偏差" in markdown


def test_only_a_tolerance_accepts_a_partial_fill(tmp_path: Path) -> None:
    """The tolerance is a deliberate escape hatch, and it must actually change the verdict."""
    root = tmp_path
    orders = _orders_csv(root)
    fills = _fills(root, [
        ("600000.XSHG", 950, 10.0),      # 5% short
        ("600001.XSHG", 500, 20.0),
        ("600002.XSHG", 300, 30.0),
    ])
    strict = _run(root, orders, fills, root / "strict")
    lenient = _run(root, orders, fills, root / "lenient", "--quantity-tolerance", "0.10")
    assert strict == 5
    assert lenient == 0


def test_only_refuses_a_fills_file_without_prices(tmp_path: Path) -> None:
    """A malformed file must be refused, not scored as 'every order missing'."""
    root = tmp_path
    orders = _orders_csv(root)
    bad = root / "bad.csv"
    bad.write_text("code,shares\n600000.XSHG,1000\n", encoding="utf-8")

    out = root / "out"
    assert _run(root, orders, bad, out) == 2
    assert not (out / "deviation_report.json").exists()


def test_only_refuses_an_orders_file_that_is_not_a_file_order_list(tmp_path: Path) -> None:
    root = tmp_path
    wrong = root / "orders.csv"
    wrong.write_text("factor_id,status\nf1,validated\n", encoding="utf-8")
    with pytest.raises(ReconcileError, match="missing columns"):
        load_orders(wrong)
