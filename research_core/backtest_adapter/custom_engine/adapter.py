from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Protocol

from contracts.backtest import BacktestRequest, BacktestResult
from research_core.backtest_adapter.base import BacktestAdapter
from research_core.backtest_adapter.custom_engine.result_mapper import map_legacy_result
from research_core.backtest_adapter.custom_engine.runner import LegacyEngineRunner


class Runner(Protocol):
    def run(self, **kwargs: Any) -> dict[str, Any]: ...


class CustomEngineAdapter(BacktestAdapter):
    """Compatibility adapter for the Chenxi A-share backtest engine."""

    engine_name = "chenxi"

    def __init__(self, runner: Runner | None = None):
        self._runner = runner

    def _resolve_runner(self, request: BacktestRequest) -> Runner:
        if self._runner is not None:
            return self._runner
        params = request.strategy_params or {}
        engine_root = (
            params.get("engine_root")
            or os.environ.get("AGENTMATRIX_CHENXI_ENGINE_ROOT")
            or os.environ.get("AGENTMATRIX_CUSTOM_ENGINE_ROOT")
        )
        if not engine_root:
            raise ValueError(
                "Set strategy_params.engine_root or AGENTMATRIX_CHENXI_ENGINE_ROOT "
                "to the Chenxi engine directory"
            )
        return LegacyEngineRunner(Path(str(engine_root)))

    def validate(self, request: BacktestRequest) -> None:
        if not request.run_id:
            raise ValueError("run_id is required")
        if not request.strategy_id:
            raise ValueError("strategy_id is required")
        if not request.start_time or not request.end_time:
            raise ValueError("start_time and end_time are required")
        params = request.strategy_params or {}
        if int(params.get("rebalance_freq", 5)) <= 0:
            raise ValueError("strategy_params.rebalance_freq must be positive")

    def run(self, request: BacktestRequest) -> BacktestResult:
        self.validate(request)
        params = request.strategy_params or {}
        runner = self._resolve_runner(request)
        strategy_name = str(params.get("strategy_name") or request.strategy_id)
        rebalance_freq = int(params.get("rebalance_freq", 5))
        fee_rate = request.commission_bps / 10_000.0
        slippage = request.slippage_bps / 10_000.0
        payload = runner.run(
            strategy_name=strategy_name,
            start=request.start_time,
            end=request.end_time,
            capital=request.initial_cash,
            benchmark=request.benchmark,
            fee_rate=fee_rate,
            slippage=slippage,
            rebalance_freq=rebalance_freq,
            data_dir=str(params.get("data_dir") or "") or None,
        )
        return map_legacy_result(
            request,
            payload,
            diagnostics={
                "strategy_name": strategy_name,
                "rebalance_freq": rebalance_freq,
                "compatibility_limitations": [
                    "Chenxi Engine may still use global initial cash and fee settings in compatibility mode.",
                    "Chenxi Engine currently uses its CSI300 benchmark implementation.",
                    "The compatibility bridge preserves existing behavior; it does not certify execution correctness.",
                ],
            },
        )
