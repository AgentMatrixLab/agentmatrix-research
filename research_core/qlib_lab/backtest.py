from __future__ import annotations
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
import pandas as pd
import numpy as np
from typing import Any
from common.paths import runtime_path
from contracts.attribution import AttributionReport, AttributionSummary
from contracts.backtest import BacktestResult, EquityPoint, HoldingSnapshot, PerformanceMetrics
from contracts.factor import FactorDefinition
from registry.factor_registry import get_factor_definition
from research_core.qlib_lab.factor_miner import QlibFactorLab


def _now_iso() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _build_definition(expression: str, name: str = "adhoc_factor") -> FactorDefinition:
    return FactorDefinition(
        factor_id=f"adhoc_{abs(hash(expression)) % 10_000_000}",
        name=name,
        expression=expression,
        description="Ad-hoc qlib expression backtest (daily robust v6.1)",
        source="adhoc",
        author="system",
    )


def run_factor_backtest(
    factor_lab: QlibFactorLab,
    *,
    run_id: str,
    strategy_id: str,
    strategy_version: str,
    benchmark: str,
    start_time: str,
    end_time: str,
    factor_expression: str | None = None,
    factor_id: str | None = None,
    top_pct: float = 0.1,
    horizon: int = 5,
    long_short: bool = False,          # ← 已改回 v1 默认值 False
    initial_cash: float = 1_000_000.0,
    cost_rate: float = 0.0015,
    neutralize: bool = True,
) -> BacktestResult:
    """日度鲁棒版 v6.1 —— long_short 默认 False"""
    
    # 1. 获取因子定义
    if factor_id:
        payload = get_factor_definition(factor_id)
        if payload is None:
            raise KeyError(f"Factor not found in registry: {factor_id}")
        definition = FactorDefinition(**{k: v for k, v in payload.items() if k in FactorDefinition.__dataclass_fields__})
    elif factor_expression:
        definition = _build_definition(factor_expression)
    else:
        raise ValueError("factor_id or factor_expression is required")

    # 2. 获取 frame
    frame = factor_lab.fetch_expression_frame(
        definition.expression,
        start_time=start_time,
        end_time=end_time,
    )
    if not isinstance(frame.index, pd.MultiIndex):
        frame = frame.set_index([frame.index.name or 'date', 'instrument'])
    frame = frame[['close', 'factor']].copy()

    # 3. 日度再平衡
    daily_dates = sorted(pd.to_datetime(frame.index.get_level_values(0).unique()))
    portfolio_returns: list[float] = []
    holdings: list[HoldingSnapshot] = []
    equity_curve: list[EquityPoint] = []
    nav = 1.0
    peak = 1.0
    drawdowns: list[float] = []

    for i in range(len(daily_dates) - horizon):
        rebal_date = daily_dates[i]
        exit_date = daily_dates[i + horizon]
        section = frame.xs(rebal_date, level=0).copy()
        if len(section) < 50:
            continue

        if neutralize:
            section['factor'] = section['factor'] - section['factor'].mean()

        section = section.sort_values('factor', ascending=False)
        n = len(section)
        long_n = int(n * top_pct)
        short_n = int(n * top_pct)

        long_stocks = section.head(long_n).index
        short_stocks = section.tail(short_n).index

        # 下一期收益
        next_section = frame.xs(exit_date, level=0)
        long_ret = (next_section['close'].reindex(long_stocks) /
                    section['close'].loc[long_stocks] - 1).mean()
        short_ret = (next_section['close'].reindex(short_stocks) /
                     section['close'].loc[short_stocks] - 1).mean()

        # 计算当日收益（根据 long_short 决定是否做空）
        if long_short:
            day_return = float(long_ret - short_ret - cost_rate * 2)
        else:
            day_return = float(long_ret - cost_rate)

        portfolio_returns.append(day_return)
        nav *= 1.0 + day_return
        peak = max(peak, nav)
        drawdown = (peak - nav) / peak if peak else 0.0
        drawdowns.append(drawdown)

        # 持仓权重
        weights = {}
        if long_short:
            weights.update({s: 1.0 / long_n for s in long_stocks})
            weights.update({s: -1.0 / short_n for s in short_stocks})
        else:
            weights.update({s: 1.0 / long_n for s in long_stocks})

        holdings.append(HoldingSnapshot(
            as_of=str(rebal_date),
            weights=weights,
            exposures={"gross": float(sum(abs(w) for w in weights.values()))}
        ))

        equity_curve.append(EquityPoint(
            timestamp=str(rebal_date),
            strategy_nav=nav,
            benchmark_nav=1.0,
            drawdown=drawdown,
        ))

    # 4. 计算指标
    ls_series = pd.Series(portfolio_returns)
    total_return = nav - 1.0
    n_periods = len(portfolio_returns)
    annualized_return = (1.0 + total_return) ** (252 / max(1, n_periods)) - 1.0 if n_periods > 0 else 0.0
    volatility = float(ls_series.std(ddof=0) * (252**0.5)) if n_periods > 1 else 0.0
    sharpe = float(ls_series.mean() / ls_series.std(ddof=0) * (252**0.5)) if n_periods > 1 and ls_series.std() > 0 else 0.0
    max_dd = max(drawdowns) if drawdowns else 0.0
    calmar = (ls_series.mean() * 252 / abs(max_dd)) if abs(max_dd) > 0 else 0.0

    metrics = PerformanceMetrics(
        total_return=total_return,
        annualized_return=annualized_return,
        benchmark_return=0.0,
        excess_return=total_return,
        max_drawdown=max_dd,
        sharpe=sharpe,
        volatility=volatility,
        turnover=2.0 if long_short else 1.0,
        win_rate=float((ls_series > 0).mean()) if n_periods > 0 else 0.0,
    )

    # 5. 构造结果
    result = BacktestResult(
        run_id=run_id,
        status="completed",
        engine="qlib_daily_robust_v6.1",
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        benchmark=benchmark,
        metrics=metrics,
        equity_curve=equity_curve,
        holdings=holdings,
        attribution=AttributionReport(
            summary=AttributionSummary(total_return=total_return),
            notes=[
                "日度再平衡 + 中性化 + 交易成本（robust v6.1）",
                "long_short 默认 False（已按 v1 习惯调整）",
                "数据默认已对齐",
            ],
        ),
        diagnostics={
            "factor_id": definition.factor_id,
            "expression": definition.expression,
            "top_pct": top_pct,
            "horizon": horizon,
            "long_short": long_short,
            "neutralize": neutralize,
            "cost_rate": cost_rate,
            "calmar": calmar,
        },
    )

    # 6. 保存 artifact
    artifact_dir = runtime_path("qlib", "backtests")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / f"{run_id}.json"
    payload = asdict(result)
    payload["saved_at"] = _now_iso()
    artifact_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    result.artifacts["result_json"] = str(artifact_path)

    return result
