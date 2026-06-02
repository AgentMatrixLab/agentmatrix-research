from __future__ import annotations

import json
import sys
import uuid
from dataclasses import asdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from common.paths import data_path
from research_core.backtest_adapter.rqalpha_pickle_parser import RQAlphaPickleParser


def parse_export(pickle_path: str | None = None) -> dict:
    target = Path(pickle_path).resolve() if pickle_path else data_path("rqalpha_exports", "sample_result.pkl")
    parser = RQAlphaPickleParser(target)
    result = parser.parse(
        run_id=f"run_{uuid.uuid4().hex[:12]}",
        strategy_id="rqalpha-buy-hold-etf",
        strategy_version="v1",
        benchmark="000300.XSHG",
    )
    payload = asdict(result)
    output_dir = data_path("rqalpha_exports")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{target.stem}_parsed_backtest.json"
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {
        "output_path": str(output_path),
        "metrics": payload["metrics"],
        "equity_points": len(payload["equity_curve"]),
        "trade_records": len(payload["trades"]),
        "holding_snapshots": len(payload["holdings"]),
        "attribution_buckets": len(payload["attribution"]["buckets"]) if payload.get("attribution") else 0,
    }
    return summary


if __name__ == "__main__":
    pickle_path = sys.argv[1] if len(sys.argv) > 1 else None
    print(json.dumps(parse_export(pickle_path), ensure_ascii=False, indent=2))
