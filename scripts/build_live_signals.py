"""Produce the live trading signals for the delivered factor set.

Why this exists
---------------
`research_core/strategy_operations/signal_pipeline.py` is a library: it has no ``__main__``, no
CLI and no file output of its own, and nothing in the repository called it. The runbook's
"live signals" step was a comment block with no command, so the deliverable the client asked
for -- 文件单 / 条件单 / Supabase rows, for a local QMT or 掘金量化 to execute and for
execution deviation to be measured against -- had no producer at all.

This script is that producer. It builds the book from the delivered low-correlation core set,
then writes:

* ``file_orders.csv``      -- 文件单, UTF-8 with BOM, the columns QMT imports directly;
* ``conditional_orders.json`` -- 条件单, one entry per order with a trigger price;
* ``supabase_rows.json``   -- the exact rows the signal table expects, for upsert.

Scope, stated plainly: nothing here pushes to Supabase. The library emits rows only, and the
repository's only write-side Supabase client needs credentials this script does not read. The
rows are written to disk in the target shape so the upload is a separate, auditable step --
and so a run without credentials still produces the deliverable.

    python -X utf8 scripts/build_live_signals.py \
        --panel-file data/factor_lab/validation_panel.parquet \
        --factor-file data/factor_lab/values/parts \
        --runs-dir data/factor_lab/validation_runs \
        --delivery-manifest delivery/delivery_manifest.csv \
        --out-dir delivery/live_signals
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_core.factor_lab.scoring import score_batch  # noqa: E402
from research_core.factor_lab.streaming_supplement import (  # noqa: E402
    composite_scores,
    ranked_block,
    unoriented_factors,
)
from research_core.strategy_operations.signal_pipeline import (  # noqa: E402
    SignalError,
    build_targets,
    diff_positions,
    to_supabase_rows,
    write_conditional_orders,
    write_file_orders,
)

CN_TZ = timezone(timedelta(hours=8))


class LiveSignalError(RuntimeError):
    """Raised when a signal set cannot be produced honestly."""


def core_factor_ids(manifest_path: Path, runs_dir: Path) -> list[str]:
    """The delivered low-correlation core: cluster representatives, highest score first.

    Falls back to every delivered factor when the manifest carries no representative, which is
    what happens if clustering did not run. Reported, never silently substituted.
    """
    frame = pd.read_csv(manifest_path, dtype=str, encoding="utf-8-sig")
    delivered = frame[frame["in_delivery_package"].str.lower() == "true"]
    if delivered.empty:
        raise LiveSignalError(
            f"{manifest_path} has no row with in_delivery_package=true; there is nothing to trade"
        )
    representatives = delivered[delivered["cluster_role"] == "representative"]
    chosen = representatives if not representatives.empty else delivered
    ordered = chosen.assign(
        _score=pd.to_numeric(chosen.get("composite"), errors="coerce").fillna(-np.inf)
    ).sort_values("_score", ascending=False)
    ids = [str(value) for value in ordered["factor_id"].tolist()]
    print(
        f"  delivered: {len(delivered)}, representatives: {len(representatives)}; "
        f"trading {len(ids)} factor(s)"
    )
    return ids


def latest_prices(panel: pd.DataFrame, trade_date: pd.Timestamp) -> dict[str, float]:
    """Closing price per code on the trade date."""
    snapshot = panel[panel["date"] == trade_date]
    if snapshot.empty:
        raise LiveSignalError(f"panel has no rows on {trade_date.date()}")
    usable = snapshot.dropna(subset=["close"])
    return {str(code): float(price) for code, price in zip(usable["code"], usable["close"])}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--panel-file", required=True)
    parser.add_argument("--factor-file", required=True, help="a parquet file or a parts directory")
    parser.add_argument("--runs-dir", required=True)
    parser.add_argument("--delivery-manifest", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--strategy-id", default="chenxi_core_v1")
    parser.add_argument("--trade-date", default="", help="ISO date; defaults to the last panel date")
    parser.add_argument("--total-value", type=float, default=10_000_000.0)
    parser.add_argument("--top-n", type=int, default=50)
    parser.add_argument("--max-weight", type=float, default=0.05)
    parser.add_argument("--price-offset-bps", type=float, default=10.0)
    parser.add_argument("--holdings", default="", help="JSON {code: shares} to rebalance from")
    args = parser.parse_args(argv)

    panel_path = Path(args.panel_file)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    panel = pd.read_parquet(panel_path)
    required = {"date", "code", "close"}
    missing = sorted(required - set(panel.columns))
    if missing:
        raise LiveSignalError(f"panel is missing columns: {', '.join(missing)}")
    panel["date"] = pd.to_datetime(panel["date"])

    results = []
    for result_path in sorted(Path(args.runs_dir).glob("*/validation_result.json")):
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        payload.setdefault("factor_id", result_path.parent.name)
        results.append(payload)
    if not results:
        raise LiveSignalError(f"no validation results under {args.runs_dir}")

    batch = score_batch(results)
    scores_by_factor = {item["factor_id"]: item for item in batch["factors"]}

    core = core_factor_ids(Path(args.delivery_manifest), Path(args.runs_dir))
    core = [factor_id for factor_id in core if factor_id in scores_by_factor] or core

    block = ranked_block(args.factor_file, factor_ids=core)
    if block.factors_missing:
        raise LiveSignalError(
            f"the delivered core set has no factor values for: {block.factors_missing[:5]}. "
            "Trading a different set than the one delivered would misrepresent the signals."
        )

    # Orient each factor by the validator's training-segment direction before scoring. Without
    # this the orders are placed on the wrong side for every reverse-signalled factor, which is
    # about half of them -- a file of confident-looking but inverted orders.
    directions: dict[str, float] = {}
    for result in results:
        factor_id = str(result.get("factor_id", ""))
        value = (result.get("training") or {}).get("direction")
        if factor_id and value is not None:
            try:
                directions[factor_id] = float(value)
            except (TypeError, ValueError):
                continue
    missing_direction = unoriented_factors(core, directions)
    if missing_direction:
        raise LiveSignalError(
            f"{len(missing_direction)} factor(s) in the delivered core set carry no training "
            f"direction, so their sign is unknown: {missing_direction[:5]}"
        )
    reverse = sorted(fid for fid in core if directions[fid] < 0)
    print(f"  directions known for {len(core)} factor(s); {len(reverse)} reverse-signalled")

    trade_date = (
        pd.Timestamp(args.trade_date) if args.trade_date else panel["date"].max()
    )
    composite = composite_scores(block, columns=core, directions=directions)
    on_date = composite[composite["date"] == trade_date]
    if on_date.empty:
        raise LiveSignalError(f"no composite scores on {trade_date.date()}")

    stock_scores = dict(zip(on_date["code"].astype(str), on_date["score"].astype(float)))
    prices = latest_prices(panel, trade_date)
    if not prices:
        raise LiveSignalError(f"no usable prices on {trade_date.date()}")

    try:
        targets = build_targets(
            stock_scores,
            total_value=args.total_value,
            prices=prices,
            top_n=args.top_n,
            max_weight=args.max_weight,
        )
    except SignalError as exc:
        raise LiveSignalError(f"could not build targets: {exc}") from exc

    holdings: dict[str, int] = {}
    if args.holdings:
        holdings = {
            str(code): int(shares)
            for code, shares in json.loads(Path(args.holdings).read_text(encoding="utf-8")).items()
        }

    try:
        orders = diff_positions(
            targets, holdings, total_value=args.total_value, prices=prices
        )
    except SignalError as exc:
        raise LiveSignalError(f"could not diff positions: {exc}") from exc

    date_text = trade_date.strftime("%Y-%m-%d")
    if not orders:
        print("  the book already matches the targets; no orders to write")
        return 0

    csv_path = write_file_orders(orders, out_dir / "file_orders.csv")
    conditional_path = write_conditional_orders(
        orders,
        out_dir / "conditional_orders.json",
        strategy_id=args.strategy_id,
        trade_date=date_text,
        price_offset_bps=args.price_offset_bps,
    )
    rows = to_supabase_rows(
        orders,
        strategy_id=args.strategy_id,
        trade_date=date_text,
        portfolio_value=args.total_value,
        price_offset_bps=args.price_offset_bps,
    )
    rows_path = out_dir / "supabase_rows.json"
    rows_path.write_text(
        json.dumps(
            {
                "table": "factor_live_signals",
                "upsert_key": ["strategy_id", "trade_date", "code"],
                "generated_at": datetime.now(CN_TZ).isoformat(timespec="seconds"),
                "pushed": False,
                "push_note": (
                    "rows only: the repository's signal library has no Supabase client, and "
                    "uploading needs credentials this step deliberately does not read"
                ),
                "rows": rows,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    buys = sum(1 for order in orders if order.side == "buy")
    summary = {
        "strategy_id": args.strategy_id,
        "trade_date": date_text,
        "generated_at": datetime.now(CN_TZ).isoformat(timespec="seconds"),
        "total_value": args.total_value,
        "top_n": args.top_n,
        "core_factors": core,
        "factor_directions": {fid: directions.get(fid) for fid in core},
        "direction_source": (
            "frozen validator `training.direction`, measured on the training split only"
        ),
        "n_targets": len(targets),
        "n_orders": len(orders),
        "n_buys": buys,
        "n_sells": len(orders) - buys,
        "artifacts": {
            "file_orders": str(csv_path),
            "conditional_orders": str(conditional_path),
            "supabase_rows": str(rows_path),
        },
    }
    (out_dir / "signal_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\nwrote {csv_path}")
    print(f"wrote {conditional_path}")
    print(f"wrote {rows_path}")
    print(f"  trade date : {date_text}")
    print(f"  targets    : {len(targets)}   orders: {len(orders)} ({buys} buys)")
    print("  note: rows are emitted, not pushed. Uploading is a separate step.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
