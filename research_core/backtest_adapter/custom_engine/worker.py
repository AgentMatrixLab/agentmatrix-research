from __future__ import annotations

import contextlib
import json
import os
import sys
import traceback
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from research_core.backtest_adapter.custom_engine.accounting import (
    summarize_legacy_accounting,
)


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: worker.py REQUEST_JSON RESULT_JSON", file=sys.stderr)
        return 2

    request_path = Path(sys.argv[1])
    result_path = Path(sys.argv[2])
    payload = json.loads(request_path.read_text(encoding="utf-8"))
    engine_root = Path(payload["engine_root"]).resolve()
    data_dir = str(payload.get("data_dir") or "")
    if data_dir:
        os.environ["DATA_DIR"] = data_dir
    sys.path.insert(0, str(engine_root))

    try:
        from engine.desk_adapter import DeskAdapter, DeskParams
        import engine.backtest as legacy_backtest

        artifact_dir = Path(payload["artifact_dir"])
        artifact_dir.mkdir(parents=True, exist_ok=True)
        legacy_backtest.RESULTS_DIR = str(artifact_dir)

        params = DeskParams(
            start=payload["start"],
            end=payload["end"],
            capital=float(payload["capital"]),
            benchmark=payload["benchmark"],
            fee_rate=float(payload["fee_rate"]),
            slippage=float(payload["slippage"]),
            rebalance_freq=int(payload["rebalance_freq"]),
        )
        with open(os.devnull, "w", encoding="utf-8") as sink, contextlib.redirect_stdout(sink):
            adapter = DeskAdapter(data_dir=data_dir) if data_dir else DeskAdapter()
            result = adapter.run(payload["strategy_name"], params)
        engine = adapter._engine
        transactions = engine.get_transactions() if engine is not None else []
        nav_frame = getattr(engine, "_last_nav_df", None)
        nav_values = nav_frame["nav"].tolist() if nav_frame is not None else []
        result["accounting"] = summarize_legacy_accounting(transactions, nav_values)
        result_path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        return 0
    except Exception:
        traceback.print_exc(file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
