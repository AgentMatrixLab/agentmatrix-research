"""
StrategyKernel 包装器 — 将回测引擎的函数式策略适配到主仓库的 StrategyKernel 接口。

用法:
  from research_core.strategy_engine.backtest_engine_kernel import (
      BacktestEngineSignalKernel,
      create_backtest_engine_strategy,
  )

  kernel = create_backtest_engine_strategy("红利策略(季)")
  decision = kernel.generate_decision(context, market_data)
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from contracts.strategy import (
    StrategyContext,
    StrategyDecision,
    StrategyMetadata,
    TargetPosition,
)
from research_core.strategy_engine.base import BaseStrategyKernel


# ═══════════════════════════════════════════════════════════════
# StrategyKernel 实现
# ═══════════════════════════════════════════════════════════════

class BacktestEngineSignalKernel(BaseStrategyKernel):
    """
    将回测引擎的函数式策略 get_signals(data) -> DataFrame(symbol, weight)
    包装为符合主仓库规范的 StrategyKernel 子类。

    重用了现有的 22 个策略，无需修改任何策略代码。
    """

    def __init__(
        self,
        metadata: StrategyMetadata,
        signal_fn: Callable[[pd.DataFrame], pd.DataFrame],
    ):
        super().__init__(metadata)
        self._signal_fn = signal_fn

    def generate_decision(
        self,
        context: StrategyContext,
        market_data: Any,
    ) -> StrategyDecision:
        """调用策略函数并将结果转换为 StrategyDecision"""
        # market_data 预期是回测引擎格式的 DataFrame
        # (包含 symbol, trade_date, close_adj, ret_1d, 等)
        if isinstance(market_data, pd.DataFrame):
            signals = self._signal_fn(market_data)
        else:
            raise TypeError(
                f"BacktestEngineSignalKernel expects pd.DataFrame, "
                f"got {type(market_data).__name__}"
            )

        targets: list[TargetPosition] = []
        if signals is not None and len(signals) > 0:
            for _, row in signals.iterrows():
                targets.append(
                    TargetPosition(
                        symbol=str(row["symbol"]),
                        target_weight=float(row.get("weight", 0)),
                        side="long",
                        reason="backtest-engine-signal",
                    )
                )

        return StrategyDecision(
            metadata=self.metadata(),
            context=context,
            targets=targets,
            raw_signals=(
                signals.to_dict(orient="records")
                if signals is not None
                else []
            ),
        )


# ═══════════════════════════════════════════════════════════════
# 工厂函数
# ═══════════════════════════════════════════════════════════════

def create_backtest_engine_strategy(
    strategy_name: str,
) -> BacktestEngineSignalKernel:
    """
    按名称查找回测引擎策略并包装为 StrategyKernel。

    参数:
        strategy_name: 策略显示名称 (如 "红利策略(季)", "小市值(月)", "Barra四因子")

    返回:
        BacktestEngineSignalKernel 实例

    异常:
        KeyError: 策略名称未找到
    """
    # 确保回测引擎在 sys.path 中
    engine_root = str(
        Path(__file__).resolve().parents[2]
        / "submissions" / "backtest_engine"
    )
    if engine_root not in sys.path:
        sys.path.insert(0, engine_root)

    from strategies import discover_strategies

    all_strategies = discover_strategies()

    # 精确匹配
    if strategy_name in all_strategies:
        signal_fn = all_strategies[strategy_name]
    else:
        # 模糊匹配
        matched = None
        for sname, fn in all_strategies.items():
            if strategy_name.lower() in sname.lower():
                matched = fn
                strategy_name = sname  # 使用精确名称
                break
        if matched is None:
            available = list(all_strategies.keys())
            raise KeyError(
                f"策略 '{strategy_name}' 未找到。"
                f"可用策略: {available}"
            )
        signal_fn = matched

    metadata = StrategyMetadata(
        strategy_id=strategy_name.replace(" ", "_").replace("(", "").replace(")", "").lower(),
        name=strategy_name,
        version="v1",
        source="internal",
        source_engine="backtest_engine",
        execution_engine="backtest_engine",
        tags=["a-share", "backtest-engine"],
    )

    return BacktestEngineSignalKernel(
        metadata=metadata,
        signal_fn=signal_fn,
    )
