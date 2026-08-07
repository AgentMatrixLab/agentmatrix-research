from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from research_core.strategy_operations.reference_data import write_index_data


def initialize_rq(module_name: str | None) -> None:
    import rqdatac

    if module_name:
        initializer = getattr(importlib.import_module(module_name), "init_rq")
        if not initializer():
            raise RuntimeError(f"RQData initialization failed through {module_name}")
        return
    username = os.getenv("RQDATA_USERNAME")
    password = os.getenv("RQDATA_PASSWORD")
    if not username or not password:
        raise RuntimeError("Set RQDATA_USERNAME and RQDATA_PASSWORD")
    rqdatac.init(username, password)


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh strategy-owned benchmark index data")
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--initializer-module", default="")
    args = parser.parse_args()
    initialize_rq(args.initializer_module or None)
    import rqdatac

    update = rqdatac.get_price(
        ["000300.XSHG"], start_date=args.start, end_date=args.end, frequency="1d",
        fields=["open", "high", "low", "close", "volume", "total_turnover"],
        adjust_type="none", skip_suspended=False, expect_df=True,
    )
    if update is None or update.empty:
        raise RuntimeError("RQData returned no CSI300 index rows")
    result = write_index_data(args.source, args.output, update.reset_index())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
