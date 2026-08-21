"""Daily automation orchestrator for AGE-8.

Usage:
    python -m research_core.daily_automation.run_daily [--days 90] [--max-codes 300]
        [--end 2026-08-12] [--skip-update] [--batch first20]

Pipeline: fetch universe -> update store (DuckDB) -> QC -> mine factors -> gate
-> register -> write markdown report. Exit code 0 on success, 1 on hard failure.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date as date_cls
from datetime import datetime
from pathlib import Path

from common.paths import data_path, runtime_path
from research_core.alpha158_lab.factors.specs import ALPHA158_FIRST_10
from research_core.daily_automation.fetcher import default_window, fetch_constituents, update_universe
from research_core.daily_automation.miner import DailyFactorMiner
from research_core.daily_automation.report import build_daily_report
from research_core.daily_automation.store import DailyStore

REPORT_DIR = data_path("daily_store", "reports")
RUN_LOG = runtime_path("daily_run_log.jsonl")


def _now_iso() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AGE-8 daily update + factor mining")
    parser.add_argument("--end", default=date_cls.today().isoformat(), help="Data end date (YYYY-MM-DD)")
    parser.add_argument("--days", type=int, default=90, help="Mining lookback in calendar days")
    parser.add_argument("--max-codes", type=int, default=None, help="Limit universe size (smoke tests)")
    parser.add_argument("--skip-update", action="store_true", help="Reuse stored data")
    parser.add_argument("--batch", choices=["first20", "first10"], default="first20")
    args = parser.parse_args(argv)

    store = DailyStore()
    codes: list[str] = []

    # ---- 1. update ------------------------------------------------------
    if args.skip_update:
        update: dict = {"skipped": True}
        codes = [r[0] for r in store.connect().execute("SELECT DISTINCT code FROM daily_kline LIMIT 500").fetchall()]
    else:
        print(f"[1/4] fetching CSI300 constituents ...", flush=True)
        codes = fetch_constituents()
        start, end = default_window(args.days)
        update = update_universe(codes, start, end, store, max_codes=args.max_codes)
        print(f"[1/4] done: ok={update['ok']} failed={update['failed']} rows={update['rows_upserted']} ({update['elapsed_s']}s)", flush=True)

    # ---- 2. QC ----------------------------------------------------------
    coverage = store.coverage_report(codes or [])
    print(f"[2/4] QC: rows={coverage['rows']} codes={coverage['codes']} last={coverage['last_date']} missing={coverage['missing_count']}", flush=True)
    if coverage["rows"] < 200 and not args.skip_update:
        print("[fatal] insufficient data after update; aborting", flush=True)
        return 1

    # ---- 3. mine ---------------------------------------------------------
    batch_names = ALPHA158_FIRST_10 if args.batch == "first10" else None
    miner = DailyFactorMiner(store, batch=batch_names)
    print(f"[3/4] mining factors (batch={args.batch}, end={args.end}, lookback={args.days}d) ...", flush=True)
    mining = miner.run(end_date=args.end, lookback_days=args.days)
    if mining["status"] == "skipped":
        print(f"[3/4] mining skipped: {mining['reason']}", flush=True)
    else:
        print(
            f"[3/4] mined: evaluated={mining['evaluated']} gated={mining['gated']} "
            f"new_registered={mining['new_registered']} duplicates={mining['duplicates_rejected']}",
            flush=True,
        )

    # ---- 4. report ---------------------------------------------------------
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    md = build_daily_report(args.end, update, coverage, mining)
    report_path = REPORT_DIR / f"{args.end}.md"
    report_path.write_text(md, encoding="utf-8")
    (REPORT_DIR / "latest.md").write_text(md, encoding="utf-8")
    print(f"[4/4] report: {report_path}", flush=True)

    record = {
        "date": args.end,
        "update": update,
        "coverage": coverage,
        "mining": {k: v for k, v in mining.items() if k not in ("results", "new_factors")},
        "report": str(report_path),
        "as_of": _now_iso(),
    }
    RUN_LOG.parent.mkdir(parents=True, exist_ok=True)
    with RUN_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    # stdout summary for cron logs / board
    print("=" * 60, flush=True)
    print(f"AGE-8 daily run {args.end}: rows={coverage['rows']} codes={coverage['codes']} "
          f"last={coverage['last_date']} | new_factors={mining.get('new_registered', 0)}", flush=True)
    print(f"report: {report_path}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
