from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

from contracts.backtest import BacktestRequest
from research_core.backtest_adapter.custom_engine import CustomEngineAdapter
from research_core.backtest_jobs.store import BacktestJobStore
from research_core.strategy_operations import load_registry, validate_result


class JobRequestError(ValueError):
    pass


class BacktestJobService:
    def __init__(self, store: BacktestJobStore, registry_path: str | Path):
        self.store = store
        self.registry_path = Path(registry_path)

    def capabilities(self) -> dict[str, Any]:
        strategies = load_registry(self.registry_path)
        return {
            "submission_enabled": os.getenv("BACKTEST_SUBMISSION_ENABLED") == "1",
            "strategies": [
                {"id": item.strategy_id, "name": item.name, "version": item.version, "status": item.status}
                for item in strategies if item.status != "disabled"
            ],
            "limits": {"max_queue": 10, "max_years": 10, "min_capital": 100_000, "max_capital": 100_000_000},
        }

    def authorize(self, supplied_token: str) -> None:
        if os.getenv("BACKTEST_SUBMISSION_ENABLED") != "1":
            raise PermissionError("backtest submission is disabled")
        expected = os.getenv("BACKTEST_SUBMISSION_TOKEN", "")
        if not expected or supplied_token != expected:
            raise PermissionError("invalid backtest submission token")

    def submit(self, raw: dict[str, Any]) -> dict[str, Any]:
        request = self.validate_request(raw)
        queued = sum(item["status"] in {"queued", "running", "validating"} for item in self.store.list(100))
        if queued >= 10:
            raise JobRequestError("backtest queue is full")
        job_id = f"bt-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}"
        return self.store.create(job_id, request)

    def validate_request(self, raw: dict[str, Any]) -> dict[str, Any]:
        definitions = {item.strategy_id: item for item in load_registry(self.registry_path) if item.status != "disabled"}
        strategy_id = str(raw.get("strategy_id") or "")
        if strategy_id not in definitions:
            raise JobRequestError("strategy_id is not in the approved registry")
        strategy = definitions[strategy_id]
        start = str(raw.get("start_date") or strategy.start_date)
        end = str(raw.get("end_date") or date.today().isoformat())
        try:
            start_date, end_date = date.fromisoformat(start), date.fromisoformat(end)
        except ValueError as exc:
            raise JobRequestError("dates must use YYYY-MM-DD") from exc
        if start_date >= end_date or (end_date - start_date).days > 3660:
            raise JobRequestError("invalid backtest date range")
        capital = float(raw.get("initial_cash", strategy.initial_cash))
        if not 100_000 <= capital <= 100_000_000:
            raise JobRequestError("initial_cash is outside allowed range")
        rebalance = int(raw.get("rebalance_freq", strategy.parameters.get("rebalance_freq", 20)))
        if not 1 <= rebalance <= 252:
            raise JobRequestError("rebalance_freq must be between 1 and 252")
        commission = float(raw.get("commission_bps", strategy.commission_bps))
        slippage = float(raw.get("slippage_bps", strategy.slippage_bps))
        if not 0 <= commission <= 100 or not 0 <= slippage <= 100:
            raise JobRequestError("fee settings must be between 0 and 100 bps")
        return {"strategy_id": strategy_id, "start_date": start, "end_date": end, "initial_cash": capital, "benchmark": strategy.benchmark, "rebalance_freq": rebalance, "commission_bps": commission, "slippage_bps": slippage}

    def run_next(self, *, engine_root: Path, data_dir: Path, result_dir: Path, adapter_factory: Callable[[], Any] = CustomEngineAdapter) -> dict[str, Any] | None:
        job = self.store.claim_next()
        if job is None:
            return None
        try:
            req = job["request"]
            strategy = {item.strategy_id: item for item in load_registry(self.registry_path)}[req["strategy_id"]]
            manifest = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))
            data_version = str(manifest.get("data_version") or "")
            if not data_version:
                raise JobRequestError("dataset manifest has no data_version")
            if req["end_date"] > data_version:
                raise JobRequestError(f"end_date exceeds available data version {data_version}")
            run_id = f"{strategy.strategy_id}-interactive-{job['job_id']}"
            self.store.update(job["job_id"], status="running", progress=15, run_id=run_id)
            request = BacktestRequest(run_id=run_id, strategy_id=strategy.strategy_id, strategy_version=strategy.version, strategy_params={**strategy.parameters, "rebalance_freq": req["rebalance_freq"], "engine_root": str(engine_root), "data_dir": str(data_dir), "strategy_name": strategy.name}, module_path="legacy://custom-engine", start_time=req["start_date"], end_time=req["end_date"], benchmark=req["benchmark"], initial_cash=req["initial_cash"], commission_bps=req["commission_bps"], slippage_bps=req["slippage_bps"], execution_engine=strategy.engine, dataset_id=data_version)
            result = adapter_factory().run(request)
            self.store.update(job["job_id"], status="validating", progress=90)
            report = validate_result(result, expected_end_date=req["end_date"], gates=strategy.quality_gates)
            result.diagnostics.update({"data_version": data_version, "quality": asdict(report), "publication_status": "review", "interactive_job_id": job["job_id"], "owner": strategy.owner})
            result_dir.mkdir(parents=True, exist_ok=True)
            target = result_dir / f"{run_id}.json"
            temporary = target.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(asdict(result), ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temporary, target)
            return self.store.update(job["job_id"], status="completed", progress=100, result_path=str(target), quality_json=json.dumps(asdict(report), ensure_ascii=False), finished_at=datetime.now(timezone.utc).isoformat())
        except Exception as exc:
            return self.store.update(job["job_id"], status="failed", progress=100, error=str(exc), finished_at=datetime.now(timezone.utc).isoformat())
