from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from contracts.backtest import BacktestRequest
from research_core.backtest_adapter.rqalpha_adapter import RQAlphaBacktestAdapter

SAMPLE_MODULES = {
    "rqalpha_buy_hold_etf": REPO_ROOT / "research_core" / "strategy_engine" / "samples" / "rqalpha_buy_hold_etf.py",
    "rqalpha_dual_ma_etf": REPO_ROOT / "research_core" / "strategy_engine" / "samples" / "rqalpha_dual_ma_etf.py",
}

SAMPLE_REQUESTS = {
    "rqalpha_buy_hold_etf": {
        "start_time": "2024-01-01",
        "end_time": "2024-12-31",
        "benchmark": "000300.XSHG",
        "initial_cash": 1000000,
        "strategy_params": {"sample_name": "rqalpha_buy_hold_etf", "frequency": "1d"},
    },
    "rqalpha_dual_ma_etf": {
        "start_time": "2023-01-01",
        "end_time": "2024-12-31",
        "benchmark": "000300.XSHG",
        "initial_cash": 1000000,
        "strategy_params": {
            "sample_name": "rqalpha_dual_ma_etf",
            "frequency": "1d",
            "short_window": 5,
            "long_window": 20,
            "symbol": "510300.XSHG",
        },
    },
}


def resolve_module_path(sample_name: str | None = None, module_path: str | None = None) -> Path:
    if module_path:
        return Path(module_path).resolve()
    if sample_name and sample_name in SAMPLE_MODULES:
        return SAMPLE_MODULES[sample_name].resolve()
    return SAMPLE_MODULES["rqalpha_buy_hold_etf"].resolve()



def build_example_plan(sample_name: str | None = None, module_path: str | None = None) -> dict:
    resolved_sample = sample_name or "rqalpha_buy_hold_etf"
    target_module = resolve_module_path(sample_name=resolved_sample, module_path=module_path)
    request_defaults = SAMPLE_REQUESTS.get(resolved_sample, SAMPLE_REQUESTS["rqalpha_buy_hold_etf"])
    strategy_name = target_module.stem.replace("_", "-")
    request = BacktestRequest(
        run_id=f"run_{uuid.uuid4().hex[:12]}",
        strategy_id=strategy_name,
        strategy_version="v1",
        strategy_params=request_defaults["strategy_params"],
        module_path=str(target_module),
        start_time=request_defaults["start_time"],
        end_time=request_defaults["end_time"],
        benchmark=request_defaults["benchmark"],
        initial_cash=request_defaults["initial_cash"],
        execution_engine="rqalpha",
    )
    adapter = RQAlphaBacktestAdapter()
    result = adapter.run(request)
    return {
        "status": result.status,
        "diagnostics": result.diagnostics,
        "artifacts": result.artifacts,
    }


if __name__ == "__main__":
    sample_name = sys.argv[1] if len(sys.argv) > 1 else None
    payload = build_example_plan(sample_name=sample_name)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
