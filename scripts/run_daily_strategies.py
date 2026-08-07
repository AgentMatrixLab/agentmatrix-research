from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from contracts.backtest import BacktestRequest
from research_core.backtest_adapter.custom_engine import CustomEngineAdapter
from research_core.strategy_operations import load_registry, validate_result


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def _data_version(manifest_path: Path) -> str:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    date_max = manifest.get("data_version") or (manifest.get("details") or {}).get("kline_adj.parquet", {}).get("date_max")
    if not date_max:
        raise ValueError("dataset manifest does not contain kline date_max")
    return str(date_max)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run and atomically publish registered strategies")
    parser.add_argument("--registry", type=Path, default=Path("config/strategy_registry.json"))
    parser.add_argument("--engine-root", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--published-dir", type=Path, default=Path("runtime/strategy_published"))
    parser.add_argument("--run-dir", type=Path, default=Path("runtime/strategy_runs"))
    parser.add_argument("--status-file", type=Path, default=Path("runtime/strategy_operations/latest.json"))
    parser.add_argument("--include-review", action="store_true", help="Run review strategies but never publish them")
    args = parser.parse_args()
    data_version = _data_version(args.data_dir / "manifest.json")
    batch_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    batch = {"batch_id": batch_id, "data_version": data_version, "started_at": datetime.now(timezone.utc).isoformat(), "strategies": []}
    for strategy in load_registry(args.registry):
        review_run = strategy.status == "review" and args.include_review
        if not strategy.runnable and not review_run:
            batch["strategies"].append({"strategy_id": strategy.strategy_id, "status": "skipped", "reason": f"registry status is {strategy.status}"})
            continue
        run_id = f"{strategy.strategy_id}-{data_version.replace('-', '')}-{batch_id}"
        request = BacktestRequest(
            run_id=run_id,
            strategy_id=strategy.strategy_id,
            strategy_version=strategy.version,
            strategy_params={**strategy.parameters, "engine_root": str(args.engine_root), "data_dir": str(args.data_dir), "strategy_name": strategy.name},
            module_path="legacy://custom-engine",
            start_time=strategy.start_date,
            end_time=data_version,
            benchmark=strategy.benchmark,
            initial_cash=strategy.initial_cash,
            commission_bps=strategy.commission_bps,
            slippage_bps=strategy.slippage_bps,
            execution_engine=strategy.engine,
            dataset_id=data_version,
        )
        try:
            result = CustomEngineAdapter().run(request)
            report = validate_result(result, expected_end_date=data_version, gates=strategy.quality_gates)
            result.diagnostics.update({"data_version": data_version, "quality": asdict(report), "owner": strategy.owner})
            run_target = args.run_dir / f"{run_id}.json"
            result.artifacts["run_json"] = str(run_target)
            _atomic_json(run_target, asdict(result))
            if not report.passed:
                batch["strategies"].append({"strategy_id": strategy.strategy_id, "run_id": run_id, "status": "quality_failed", "artifact": str(run_target), "errors": list(report.errors), "warnings": list(report.warnings)})
                continue
            if review_run:
                batch["strategies"].append({"strategy_id": strategy.strategy_id, "run_id": run_id, "status": "quarantined", "artifact": str(run_target), "warnings": list(report.warnings)})
                continue
            target = args.published_dir / f"{strategy.strategy_id}.json"
            result.artifacts["result_json"] = str(target)
            _atomic_json(target, asdict(result))
            batch["strategies"].append({"strategy_id": strategy.strategy_id, "run_id": run_id, "status": "published", "warnings": list(report.warnings)})
        except Exception as exc:
            batch["strategies"].append({"strategy_id": strategy.strategy_id, "run_id": run_id, "status": "failed", "error": str(exc)})
    batch["finished_at"] = datetime.now(timezone.utc).isoformat()
    _atomic_json(args.status_file, batch)
    print(json.dumps(batch, ensure_ascii=False, indent=2))
    return 1 if any(item["status"] in {"failed", "quality_failed"} for item in batch["strategies"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
