"""
BacktestEngineAdapter — 将回测引擎接入 agentmatrix-research 的 BacktestAdapter 接口。

完整数据流:
  BacktestRequest → 策略查找 → BacktestEngine.run_strategy()
  → 捕获 (nav_df, metrics_dict, trade_log, snapshots)
  → 转换为 BacktestResult (PerformanceMetrics + EquityPoint[] + TradeRecord[])
  → 持久化 → 返回
"""

from __future__ import annotations

import os
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from common.paths import data_path, runtime_path
from contracts.attribution import AttributionReport, AttributionSummary
from contracts.backtest import (
    BacktestRequest,
    BacktestResult,
    EquityPoint,
    HoldingSnapshot,
    PerformanceMetrics,
    TradeRecord,
)
from research_core.backtest_adapter.base import BacktestAdapter


# ═══════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════

def _now_iso() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _extract_pct(text: str) -> float:
    """从 '12.34%' / '-5.67%' 提取 0.1234 / -0.0567"""
    text = str(text).strip().rstrip("%")
    return float(text) / 100.0


def _extract_float(text: str) -> float:
    """从 '1.23' / '45天' 提取浮点数"""
    text = str(text).strip()
    # 去掉中文后缀
    cleaned = "".join(c for c in text if c.isdigit() or c in ".-")
    return float(cleaned) if cleaned else 0.0


# ═══════════════════════════════════════════════════════════════
# 引擎实例缓存 (避免每次 run() 都重新加载 8M+ 行 Parquet)
# ═══════════════════════════════════════════════════════════════

_ENGINE_CACHE: dict[str, Any] = {}


def _get_engine(data_dir: str):
    """获取或创建 BacktestEngine 实例 (按 data_dir 缓存)"""
    if data_dir not in _ENGINE_CACHE:
        # 确保 submissions/backtest_engine 在 sys.path 中
        engine_root = str(
            Path(__file__).resolve().parents[2]
            / "submissions" / "backtest_engine"
        )
        if engine_root not in sys.path:
            sys.path.insert(0, engine_root)

        from engine.backtest import BacktestEngine

        os.makedirs(data_dir, exist_ok=True)
        engine = BacktestEngine(data_dir=data_dir)
        _ENGINE_CACHE[data_dir] = engine

    return _ENGINE_CACHE[data_dir]


def _discover_strategy(name: str):
    """按名称查找策略函数"""
    engine_root = str(
        Path(__file__).resolve().parents[2]
        / "submissions" / "backtest_engine"
    )
    if engine_root not in sys.path:
        sys.path.insert(0, engine_root)

    from strategies import discover_strategies

    all_strategies = discover_strategies()
    if name in all_strategies:
        return all_strategies[name]

    # 模糊匹配
    for sname, fn in all_strategies.items():
        if name.lower() in sname.lower():
            return fn

    available = list(all_strategies.keys())
    raise KeyError(
        f"策略 '{name}' 未找到。可用策略: {available}"
    )


# ═══════════════════════════════════════════════════════════════
# 结果转换
# ═══════════════════════════════════════════════════════════════

def _metrics_dict_to_performance(
    metrics: dict,
    benchmark_return: float = 0.0,
) -> PerformanceMetrics:
    """将回测引擎的中文键指标字典转为 PerformanceMetrics dataclass"""
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
        win_rate=_extract_pct(metrics.get("交易胜率", "0%")),
    )


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


def _trade_log_to_records(trade_log: list[dict]) -> list[TradeRecord]:
    """将引擎的 _trade_log 转为 TradeRecord 列表"""
    records: list[TradeRecord] = []
    for t in trade_log:
        records.append(
            TradeRecord(
                traded_at=str(t.get("trade_date", "")),
                symbol=str(t["symbol"]),
                side="sell",
                quantity=float(t["shares"]),
                price=float(t["exit_price"]),
                commission=0.0,
                slippage=0.0,
                reason="rebalance",
            )
        )
    return records


def _snapshots_to_holdings(
    snapshots: list[dict],
) -> list[HoldingSnapshot]:
    """将引擎的 _position_snapshots 转为 HoldingSnapshot 列表"""
    result: list[HoldingSnapshot] = []
    for snap in snapshots:
        weights: dict[str, float] = {}
        total_value = 0.0
        for h in snap.get("holdings", []):
            weights[str(h["symbol"])] = float(h.get("weight", 0)) / 100.0
            total_value += float(h.get("value", 0))
        result.append(
            HoldingSnapshot(
                as_of=str(snap["date"]),
                weights=weights,
                exposures={"gross_value": total_value},
            )
        )
    return result


# ═══════════════════════════════════════════════════════════════
# 适配器主类
# ═══════════════════════════════════════════════════════════════

class BacktestEngineAdapter(BacktestAdapter):
    """
    自定义回测引擎适配器 — 完整的投资组合模拟。

    与主仓库 QlibBacktestAdapter (因子评分) 不同，
    此适配器执行完整的投资组合模拟:
      - 逐日循环, T+1 执行
      - 现金管理, 头寸追踪
      - 手续费/印花税/滑点
      - A 股整手约束 (100 股主板, 200 股科创板)
      - 真实数据管道 (SIM API → Parquet)
    """

    engine_name = "backtest_engine"

    def validate(self, request: BacktestRequest) -> None:
        if not request.strategy_id:
            raise ValueError("strategy_id is required")
        if not request.start_time or not request.end_time:
            raise ValueError("start_time and end_time are required")

    def run(self, request: BacktestRequest) -> BacktestResult:
        self.validate(request)

        # 1. 解析数据目录
        data_dir = os.environ.get(
            "BACKTEST_ENGINE_DATA_DIR",
            str(data_path("backtest_engine")),
        )

        # 2. 查找策略函数
        signal_fn = _discover_strategy(request.strategy_id)

        # 3. 初始化引擎 (缓存)
        engine = _get_engine(data_dir)

        # 4. 运行回测
        rebalance_freq = int(
            request.strategy_params.get("rebalance_freq", 5)
        )
        nav_df, metrics_dict = engine.run_strategy(
            signal_fn=signal_fn,
            name=request.strategy_id,
            rebalance_freq=rebalance_freq,
            start_date=request.start_time,
            end_date=request.end_time,
        )

        # 5. 提取引擎内部状态
        trade_log = getattr(engine, "_trade_log", [])
        snapshots = getattr(engine, "_position_snapshots", [])

        # 6. 计算基准收益
        if "benchmark" in nav_df.columns:
            bm_first = float(nav_df["benchmark"].iloc[0])
            bm_last = float(nav_df["benchmark"].iloc[-1])
            benchmark_return = (bm_last / bm_first - 1.0) if bm_first > 0 else 0.0
        else:
            benchmark_return = 0.0

        # 7. 转换为类型化结果
        metrics = _metrics_dict_to_performance(
            metrics_dict, benchmark_return
        )
        equity_curve = _nav_to_equity_curve(nav_df)
        trades = _trade_log_to_records(trade_log)
        holdings = _snapshots_to_holdings(snapshots)

        # 8. 归因报告
        fee_drag = -float(
            sum(t.get("commission", 0) for t in trade_log)
            + sum(t.get("stamp_tax", 0) for t in trade_log)
        ) / request.initial_cash if request.initial_cash > 0 else 0.0

        attribution = AttributionReport(
            summary=AttributionSummary(
                total_return=metrics.total_return,
                benchmark_return=benchmark_return,
                excess_return=metrics.total_return - benchmark_return,
                fee_drag=fee_drag,
                slippage_drag=0.0,
                cash_drag=0.0,
            ),
            notes=[
                "Backtest engine full portfolio simulation with T+1 execution.",
                f"Fee rate: {getattr(engine, 'fee_rate', 'default')}, "
                f"Rebalance freq: {rebalance_freq} days.",
            ],
            methodology="backtest-engine-v1",
        )

        # 9. 构建结果
        result = BacktestResult(
            run_id=request.run_id,
            status="completed",
            engine=self.engine_name,
            strategy_id=request.strategy_id,
            strategy_version=request.strategy_version,
            benchmark=request.benchmark,
            metrics=metrics,
            equity_curve=equity_curve,
            trades=trades,
            holdings=holdings,
            attribution=attribution,
            diagnostics={
                "strategy_params": request.strategy_params,
                "rebalance_freq": rebalance_freq,
                "trade_count": len(trade_log),
                "snapshot_count": len(snapshots),
                "trading_days": len(nav_df),
                "engine_name": self.engine_name,
            },
        )

        # 10. 持久化结果
        result_dir = runtime_path("backtest_engine", "results")
        result_dir.mkdir(parents=True, exist_ok=True)
        result_path = result_dir / f"{request.run_id}.json"

        import json

        result_path.write_text(
            json.dumps(asdict(result), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        result.artifacts["result_json"] = str(result_path)

        return result
