from __future__ import annotations

from contracts.backtest import BacktestRequest, BacktestResult
from research_core.backtest_adapter.base import BacktestAdapter
from research_core.qlib_lab.backtest import run_factor_backtest
from research_core.qlib_lab.factor_miner import QlibFactorLab
from research_core.qlib_lab.runtime import QlibWorkspaceConfig


class QlibBacktestAdapter(BacktestAdapter):
    engine_name = "qlib"

    def validate(self, request: BacktestRequest) -> None:
        if not request.start_time or not request.end_time:
            raise ValueError("start_time and end_time are required")
        params = request.strategy_params or {}
        if not params.get("factor_expression") and not params.get("factor_id"):
            raise ValueError("QlibBacktestAdapter requires strategy_params.factor_expression or strategy_params.factor_id")

    def run(self, request: BacktestRequest) -> BacktestResult:
        self.validate(request)

        config = QlibWorkspaceConfig.from_env()
        factor_lab = QlibFactorLab(config=config)
        return run_factor_backtest(
            factor_lab,
            run_id=request.run_id,
            strategy_id=request.strategy_id,
            strategy_version=request.strategy_version,
            benchmark=request.benchmark,
            start_time=request.start_time,
            end_time=request.end_time,
            factor_expression=request.strategy_params.get("factor_expression"),
            factor_id=request.strategy_params.get("factor_id"),
            top_k=int(request.strategy_params.get("top_k", 30)),
            horizon=int(request.strategy_params.get("horizon", 5)),
            long_short=bool(request.strategy_params.get("long_short", False)),
            initial_cash=request.initial_cash,
        )
