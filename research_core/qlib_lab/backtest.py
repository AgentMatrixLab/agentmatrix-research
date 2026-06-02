from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

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
        description="Ad-hoc qlib expression backtest",
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
    top_k: int = 30,
    horizon: int = 5,
    long_short: bool = False,
    initial_cash: float = 1_000_000.0,
) -> BacktestResult:
    if factor_id:
        payload = get_factor_definition(factor_id)
        if payload is None:
            raise KeyError(f"Factor not found in registry: {factor_id}")
        definition = FactorDefinition(**{key: value for key, value in payload.items() if key in FactorDefinition.__dataclass_fields__})
    elif factor_expression:
        definition = _build_definition(factor_expression)
    else:
        raise ValueError("factor_id or factor_expression is required")

    frame = factor_lab.fetch_expression_frame(
        definition.expression,
        start_time=start_time,
        end_time=end_time,
    )
    frame["future_return"] = frame.groupby(level=1)["close"].shift(-horizon) / frame["close"] - 1.0
    frame = frame.dropna(subset=["factor", "future_return"])

    portfolio_returns: list[float] = []
    holdings: list[HoldingSnapshot] = []
    nav = 1.0
    peak = 1.0
    drawdowns: list[float] = []
    equity_curve: list[EquityPoint] = []

    for as_of, daily in frame.groupby(level=0):
        ranked = daily.sort_values("factor", ascending=False)
        long_leg = ranked.head(top_k)["future_return"]
        if long_short:
            short_leg = ranked.tail(top_k)["future_return"]
            day_return = float(long_leg.mean() - short_leg.mean())
            weights = {idx[1]: 1 / top_k for idx in long_leg.index}
            for idx in short_leg.index:
                weights[idx[1]] = -1 / top_k
        else:
            day_return = float(long_leg.mean())
            weights = {idx[1]: 1 / top_k for idx in long_leg.index}

        portfolio_returns.append(day_return)
        nav *= 1.0 + day_return
        peak = max(peak, nav)
        drawdown = (peak - nav) / peak if peak else 0.0
        drawdowns.append(drawdown)

        holdings.append(
            HoldingSnapshot(
                as_of=str(as_of),
                weights=weights,
                exposures={"gross": float(sum(abs(weight) for weight in weights.values()))},
            )
        )
        equity_curve.append(
            EquityPoint(
                timestamp=str(as_of),
                strategy_nav=nav,
                benchmark_nav=1.0,
                drawdown=drawdown,
            )
        )

    total_return = nav - 1.0
    annualized_return = (1.0 + total_return) ** (252 / max(1, len(portfolio_returns))) - 1.0
    volatility = float(pd.Series(portfolio_returns).std(ddof=0) * (252**0.5)) if portfolio_returns else 0.0
    sharpe = (
        float(pd.Series(portfolio_returns).mean() / pd.Series(portfolio_returns).std(ddof=0) * (252**0.5))
        if len(portfolio_returns) > 1 and pd.Series(portfolio_returns).std(ddof=0) > 0
        else 0.0
    )
    win_rate = float(sum(1 for value in portfolio_returns if value > 0) / len(portfolio_returns)) if portfolio_returns else 0.0
    turnover = 2.0 if long_short else 1.0

    metrics = PerformanceMetrics(
        total_return=total_return,
        annualized_return=annualized_return,
        benchmark_return=0.0,
        excess_return=total_return,
        max_drawdown=max(drawdowns) if drawdowns else 0.0,
        sharpe=sharpe,
        volatility=volatility,
        turnover=turnover,
        win_rate=win_rate,
    )
    result = BacktestResult(
        run_id=run_id,
        status="completed",
        engine="qlib",
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        benchmark=benchmark,
        metrics=metrics,
        equity_curve=equity_curve,
        holdings=holdings,
        attribution=AttributionReport(
            summary=AttributionSummary(total_return=total_return),
            notes=[
                "Qlib factor backtest uses equal-weight cross-sectional scoring.",
                "Use this result for factor validity screening before moving to a full execution engine.",
            ],
        ),
        diagnostics={
            "factor_id": definition.factor_id,
            "expression": definition.expression,
            "top_k": top_k,
            "horizon": horizon,
            "long_short": long_short,
        },
    )

    artifact_dir = runtime_path("qlib", "backtests")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / f"{run_id}.json"
    payload = asdict(result)
    payload["saved_at"] = _now_iso()
    artifact_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    result.artifacts["result_json"] = str(artifact_path)
    artifact_path.write_text(json.dumps(asdict(result), ensure_ascii=False, indent=2), encoding="utf-8")
    return result
