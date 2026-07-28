"""
QlibEngineAdapter — 将回测引擎的 QlibBacktestRunner 接入 BacktestAdapter 接口。

与主仓库 QlibBacktestAdapter (简化因子评分) 不同，此适配器:
  - 真正调用 Microsoft Qlib 的 backtest() 引擎
  - 使用 SimulatorExecutor + TopkDropoutStrategy
  - 完整投资组合约束: 手续费/印花税/滑点/整手
  - 通过 ParquetToQlibConverter 确保 bin 数据就绪
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from common.paths import data_path, runtime_path
from contracts.attribution import AttributionReport, AttributionSummary
from contracts.backtest import (
    BacktestRequest,
    BacktestResult,
    EquityPoint,
    PerformanceMetrics,
)
from research_core.backtest_adapter.backtest_engine_adapter import (
    _extract_float,
    _extract_pct,
)
from research_core.backtest_adapter.base import BacktestAdapter


# ═══════════════════════════════════════════════════════════════
# 引擎实例缓存
# ═══════════════════════════════════════════════════════════════

_QLIB_RUNNER_CACHE: dict[str, Any] = {}


def _get_engine_root() -> str:
    return str(
        Path(__file__).resolve().parents[2]
        / "submissions" / "backtest_engine"
    )


def _get_qlib_runner():
    """获取或创建 QlibBacktestRunner (单例)"""
    cache_key = "default"
    if cache_key not in _QLIB_RUNNER_CACHE:
        engine_root = _get_engine_root()
        if engine_root not in sys.path:
            sys.path.insert(0, engine_root)

        from engine.qlib_bridge import QlibBacktestRunner, ensure_qlib_data

        # 确保 Qlib bin 数据存在
        ensure_qlib_data()

        runner = QlibBacktestRunner()
        _QLIB_RUNNER_CACHE[cache_key] = runner

    return _QLIB_RUNNER_CACHE[cache_key]


def _nav_to_equity_curve(nav_df: pd.DataFrame) -> list[EquityPoint]:
    """将 nav DataFrame 转为 EquityPoint 列表"""
    cummax = nav_df["nav"].cummax()
    points: list[EquityPoint] = []
    for idx, row in nav_df.iterrows():
        dd = (row["nav"] / cummax[idx] - 1.0) if cummax[idx] > 0 else 0.0
        benchmark_nav = float(row.get("benchmark", 1.0))
        points.append(
            EquityPoint(
                timestamp=str(idx)[:19],
                strategy_nav=float(row["nav"]),
                benchmark_nav=benchmark_nav,
                drawdown=float(dd),
            )
        )
    return points


def _metrics_dict_to_performance(
    metrics: dict,
    benchmark_return: float = 0.0,
) -> PerformanceMetrics:
    """将中文键指标字典转为 PerformanceMetrics"""
    total_return = _extract_pct(metrics.get("总收益率", "0%"))
    return PerformanceMetrics(
        total_return=total_return,
        annualized_return=_extract_pct(metrics.get("年化收益率", "0%")),
        benchmark_return=benchmark_return,
        excess_return=total_return - benchmark_return,
        max_drawdown=_extract_pct(metrics.get("最大回撤", "0%")),
        sharpe=_extract_float(metrics.get("夏普比率", "0")),
        volatility=_extract_pct(metrics.get("年化波动率", "0%")),
        turnover=_extract_pct(metrics.get("年化换手率", "0%")),
        win_rate=_extract_pct(metrics.get("日胜率", "0%")),
    )


# ═══════════════════════════════════════════════════════════════
# 适配器主类
# ═══════════════════════════════════════════════════════════════

class QlibEngineAdapter(BacktestAdapter):
    """
    Qlib 真实引擎适配器 — 调用 Microsoft Qlib backtest()。

    与主仓库 QlibBacktestAdapter (因子评分, 不走 Qlib 引擎) 互补:
      - QlibBacktestAdapter: 快速因子筛选, 无交易成本
      - QlibEngineAdapter:   完整执行模拟, 真正 Qlib 引擎

    依赖:
      - pyqlib 已安装
      - Qlib bin 数据已通过 ParquetToQlibConverter 生成
    """

    engine_name = "qlib_engine"

    def validate(self, request: BacktestRequest) -> None:
        if not request.strategy_id:
            raise ValueError("strategy_id is required")
        if not request.start_time or not request.end_time:
            raise ValueError("start_time and end_time are required")

    def run(self, request: BacktestRequest) -> BacktestResult:
        self.validate(request)

        runner = _get_qlib_runner()

        # 解析参数
        rebalance_freq = int(
            request.strategy_params.get("rebalance_freq", 21)
        )
        topk = int(request.strategy_params.get("topk", 50))

        # 运行 Qlib 回测
        nav_df, metrics_dict = runner.run_strategy(
            strategy_name=request.strategy_id,
            rebalance_freq=rebalance_freq,
            start_time=request.start_time,
            end_time=request.end_time,
            topk=topk,
        )

        # 基准收益
        if "benchmark" in nav_df.columns:
            bm_first = float(nav_df["benchmark"].iloc[0])
            bm_last = float(nav_df["benchmark"].iloc[-1])
            benchmark_return = (bm_last / bm_first - 1.0) if bm_first > 0 else 0.0
        else:
            benchmark_return = 0.0

        # 转换为类型化结果
        metrics = _metrics_dict_to_performance(
            metrics_dict, benchmark_return
        )
        equity_curve = _nav_to_equity_curve(nav_df)

        result = BacktestResult(
            run_id=request.run_id,
            status="completed",
            engine=self.engine_name,
            strategy_id=request.strategy_id,
            strategy_version=request.strategy_version,
            benchmark=request.benchmark,
            metrics=metrics,
            equity_curve=equity_curve,
            trades=[],
            holdings=[],
            attribution=AttributionReport(
                summary=AttributionSummary(
                    total_return=metrics.total_return,
                    benchmark_return=benchmark_return,
                    excess_return=metrics.total_return - benchmark_return,
                ),
                notes=[
                    "Qlib backtest with SimulatorExecutor + TopkDropoutStrategy.",
                    "Uses Microsoft Qlib backtest() engine with full portfolio constraints.",
                    f"Fee rate: 0.03% buy, 0.13% sell (incl. stamp tax). "
                    f"Rebalance freq: {rebalance_freq} days.",
                ],
                methodology="qlib-engine-v1",
            ),
            diagnostics={
                "strategy_params": request.strategy_params,
                "qlib_engine": True,
                "rebalance_freq": rebalance_freq,
                "topk": topk,
            },
        )

        # 持久化
        result_dir = runtime_path("backtest_engine", "results")
        result_dir.mkdir(parents=True, exist_ok=True)
        result_path = result_dir / f"{request.run_id}_qlib.json"
        result_path.write_text(
            json.dumps(asdict(result), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        result.artifacts["result_json"] = str(result_path)

        return result
