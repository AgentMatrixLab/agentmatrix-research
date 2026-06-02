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


def execute_request(sample_name: str = "rqalpha_buy_hold_etf") -> dict:
    from research_core.backtest_adapter.example_rqalpha_plan import SAMPLE_MODULES, SAMPLE_REQUESTS

    try:
        from rqalpha import run as rqalpha_run
    except ImportError as exc:
        raise RuntimeError("rqalpha 未安装，无法执行真实回测。请先在服务器环境安装 rqalpha 与对应数据依赖。") from exc

    target_module = SAMPLE_MODULES[sample_name].resolve()
    defaults = SAMPLE_REQUESTS[sample_name]
    request = BacktestRequest(
        run_id=f"run_{uuid.uuid4().hex[:12]}",
        strategy_id=target_module.stem.replace("_", "-"),
        strategy_version="v1",
        strategy_params=defaults["strategy_params"],
        module_path=str(target_module),
        start_time=defaults["start_time"],
        end_time=defaults["end_time"],
        benchmark=defaults["benchmark"],
        initial_cash=defaults["initial_cash"],
        execution_engine="rqalpha",
    )

    adapter = RQAlphaBacktestAdapter()
    plan = adapter.build_execution_plan(request)
    artifact_dir = Path(plan["artifact_paths"]["artifact_dir"])
    artifact_dir.mkdir(parents=True, exist_ok=True)
    Path(plan["artifact_paths"]["report_save_path"]).mkdir(parents=True, exist_ok=True)
    rqalpha_run(plan["rqalpha_config"])
    parsed = adapter.run(request)
    return {
        "status": parsed.status,
        "metrics": {
            "annualized_return": parsed.metrics.annualized_return,
            "benchmark_return": parsed.metrics.benchmark_return,
            "max_drawdown": parsed.metrics.max_drawdown,
            "sharpe": parsed.metrics.sharpe,
            "total_return": parsed.metrics.total_return,
            "volatility": parsed.metrics.volatility,
        },
        "artifacts": parsed.artifacts,
    }


if __name__ == "__main__":
    sample_name = sys.argv[1] if len(sys.argv) > 1 else "rqalpha_buy_hold_etf"
    print(json.dumps(execute_request(sample_name), ensure_ascii=False, indent=2))
