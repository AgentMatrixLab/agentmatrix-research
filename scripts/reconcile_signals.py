"""Compare the delivered live signals against actual fills.

The brief asks for signals "供本地 QMT 或掘金量化对照执行偏差" -- for a local QMT or
掘金量化 terminal to execute and for execution deviation to be measured against. The
repository can do the measuring (`signal_pipeline.reconcile_execution` returns missing fills,
unexpected fills, quantity breaks and price slippage as a `DeviationReport`) but nothing called
it: `build_live_signals.py` writes the orders and stops there.

This is the other half. It reads the orders that were delivered, reads the fills the trading
terminal produced, and writes the deviation report as JSON and markdown.

    python -X utf8 scripts/reconcile_signals.py \
        --orders delivery/live_signals/file_orders.csv \
        --fills  delivery/live_signals/fills_2026-08-31.csv \
        --out-dir delivery/live_signals

The fills file needs `code`, `shares` and `price` (and ideally `side`); extra columns are
ignored. Partial fills are reported as quantity breaks unless `--quantity-tolerance` allows
them -- a half-filled basket is a different portfolio from the one that was validated, so the
default is that every share must match.

Exit codes: 0 = no deviation, 5 = deviations found, 2 = bad input.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_core.strategy_operations.signal_pipeline import (  # noqa: E402
    FILE_ORDER_COLUMNS,
    Order,
    SignalError,
    reconcile_execution,
)


class ReconcileError(RuntimeError):
    """Raised when the two sides of the comparison cannot be read honestly."""


def load_orders(path: Path) -> list[Order]:
    """Rebuild the delivered orders from the file-order CSV.

    ``current_weight`` is not carried by the CSV and is not used by reconciliation (the report
    is about quantities, prices and presence), so it is reconstructed as 0.0 rather than
    invented from something else.
    """
    if not path.is_file():
        raise ReconcileError(f"orders file not found: {path}")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or [])
        required = {"code", "side", "shares", "reference_price"}
        missing = sorted(required - columns)
        if missing:
            raise ReconcileError(
                f"{path.name} is missing columns: {', '.join(missing)}. Expected the file "
                f"orders produced by build_live_signals ({', '.join(FILE_ORDER_COLUMNS)})."
            )
        orders: list[Order] = []
        for row in reader:
            orders.append(
                Order(
                    code=str(row["code"]),
                    side=str(row["side"]),
                    shares=int(float(row["shares"])),
                    reference_price=float(row["reference_price"]),
                    target_weight=float(row.get("target_weight") or 0.0),
                    current_weight=0.0,
                    reason=str(row.get("reason") or ""),
                )
            )
    if not orders:
        raise ReconcileError(f"{path.name} contains no orders")
    return orders


def load_fills(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise ReconcileError(f"fills file not found: {path}")
    fills = pd.read_csv(path, dtype=str, encoding="utf-8-sig")
    missing = sorted({"code", "shares", "price"} - set(fills.columns))
    if missing:
        raise ReconcileError(f"{path.name} is missing columns: {', '.join(missing)}")
    return fills


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--orders", required=True, help="file_orders.csv from build_live_signals")
    parser.add_argument("--fills", required=True, help="the trading terminal's fills CSV")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--strategy-id", default="chenxi_core_v1")
    parser.add_argument("--trade-date", default="", help="defaults to the orders file's trade date")
    parser.add_argument(
        "--quantity-tolerance",
        type=float,
        default=0.0,
        help="allowed shortfall as a FRACTION of the intended quantity; 0.0 requires an exact match",
    )
    parser.add_argument("--slippage-warn-bps", type=float, default=20.0)
    args = parser.parse_args(argv)

    orders_path = Path(args.orders)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        orders = load_orders(orders_path)
        fills = load_fills(Path(args.fills))
    except ReconcileError as exc:
        print(json.dumps({"status": "error", "reason": str(exc)}, ensure_ascii=False, indent=2))
        return 2

    trade_date = args.trade_date or f"{orders_path.parent.name}"
    summary_path = orders_path.parent / "signal_summary.json"
    if not args.trade_date and summary_path.is_file():
        try:
            trade_date = str(json.loads(summary_path.read_text(encoding="utf-8"))["trade_date"])
        except (OSError, json.JSONDecodeError, KeyError):
            pass

    try:
        report = reconcile_execution(
            orders,
            fills,
            trade_date=trade_date,
            strategy_id=args.strategy_id,
            quantity_tolerance=args.quantity_tolerance,
            slippage_warn_bps=args.slippage_warn_bps,
        )
    except SignalError as exc:
        print(json.dumps({"status": "error", "reason": str(exc)}, ensure_ascii=False, indent=2))
        return 2

    payload = report.as_dict()
    json_path = out_dir / "deviation_report.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path = out_dir / "deviation_report.md"
    markdown_path.write_text(report.render_markdown(), encoding="utf-8")

    print(f"wrote {json_path}")
    print(f"wrote {markdown_path}")
    print(f"  intended orders : {len(orders)}")
    print(f"  intended notional: {report.intended_notional:,.2f}")
    print(f"  filled notional  : {report.filled_notional:,.2f}")
    print(f"  fill ratio       : {report.fill_ratio:.4f}")
    print(f"  clean            : {report.is_clean}")
    print(f"  missing          : {len(report.missing)}")
    print(f"  unexpected       : {len(report.unexpected)}")
    print(f"  quantity breaks  : {len(report.quantity_breaks)}")
    print(f"  price slippage   : {len(report.price_slippage)}")
    print()
    print(report.render_markdown())
    return 0 if report.is_clean else 5


if __name__ == "__main__":
    raise SystemExit(main())
