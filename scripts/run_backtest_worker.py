from __future__ import annotations

import argparse
import fcntl
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from research_core.backtest_jobs import BacktestJobService, BacktestJobStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the controlled Quant Desk backtest worker")
    parser.add_argument("--db", type=Path, default=Path("runtime/backtest_jobs/jobs.sqlite3"))
    parser.add_argument("--registry", type=Path, default=Path("config/strategy_registry.json"))
    parser.add_argument("--engine-root", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--result-dir", type=Path, default=Path("runtime/strategy_runs"))
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    parser.add_argument("--lock-file", type=Path, default=Path("runtime/strategy_operations/daily.lock"))
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    service = BacktestJobService(BacktestJobStore(args.db), args.registry)
    args.lock_file.parent.mkdir(parents=True, exist_ok=True)
    while True:
        with args.lock_file.open("a+") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                job = None
            else:
                job = service.run_next(engine_root=args.engine_root, data_dir=args.data_dir, result_dir=args.result_dir)
                fcntl.flock(lock, fcntl.LOCK_UN)
        if args.once:
            return 0
        if job is None:
            time.sleep(max(args.poll_seconds, 0.2))


if __name__ == "__main__":
    raise SystemExit(main())
