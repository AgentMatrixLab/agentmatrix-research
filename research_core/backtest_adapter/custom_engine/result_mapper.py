from __future__ import annotations

from typing import Any

from contracts.backtest import (
    BacktestRequest,
    BacktestResult,
    EquityPoint,
    HoldingSnapshot,
    PerformanceMetrics,
    TradeRecord,
)


def _number(payload: dict[str, Any], key: str, default: float = 0.0) -> float:
    value = payload.get(key, default)
    if value is None:
        return default
    return float(value)


def _canonical_symbol(value: Any) -> str:
    symbol = str(value or "").upper()
    if not symbol or "." in symbol:
        return symbol
    if symbol.startswith(("4", "8")):
        return f"{symbol}.BJ"
    if symbol.startswith(("0", "2", "3")):
        return f"{symbol}.SZ"
    if symbol.startswith(("5", "6", "9")):
        return f"{symbol}.SH"
    return symbol


def map_legacy_result(
    request: BacktestRequest,
    payload: dict[str, Any],
    *,
    diagnostics: dict[str, Any] | None = None,
) -> BacktestResult:
    """Map the existing DeskAdapter payload into the AgentMatrix contract.

    Legacy drawdown series use negative values. AgentMatrix equity points keep
    that convention, while `PerformanceMetrics.max_drawdown` is a positive
    magnitude.
    """

    raw_metrics = payload.get("kpis") or {}
    equity_curve = [
        EquityPoint(
            timestamp=str(point.get("date", "")),
            strategy_nav=_number(point, "nav", 1.0),
            benchmark_nav=_number(point, "benchmark", 1.0),
            drawdown=min(0.0, _number(point, "drawdown")),
        )
        for point in payload.get("nav", [])
    ]

    benchmark_return = 0.0
    if len(equity_curve) >= 2 and equity_curve[0].benchmark_nav:
        benchmark_return = (
            equity_curve[-1].benchmark_nav / equity_curve[0].benchmark_nav - 1.0
        )

    total_return = _number(raw_metrics, "total_return")
    accounting = payload.get("accounting") or {}
    turnover = _number(accounting, "turnover", _number(raw_metrics, "turnover"))
    metrics = PerformanceMetrics(
        total_return=total_return,
        annualized_return=_number(raw_metrics, "annual_return"),
        benchmark_return=benchmark_return,
        excess_return=total_return - benchmark_return,
        max_drawdown=abs(_number(raw_metrics, "max_drawdown")),
        sharpe=_number(raw_metrics, "sharpe"),
        volatility=_number(raw_metrics, "volatility"),
        turnover=turnover,
        win_rate=_number(raw_metrics, "win_rate"),
    )

    raw_holdings = payload.get("holdings", [])
    holdings: list[HoldingSnapshot] = []
    if raw_holdings:
        as_of = str(payload.get("as_of") or (equity_curve[-1].timestamp if equity_curve else ""))
        weights = {
            _canonical_symbol(item.get("symbol") or item.get("code")): _number(item, "weight")
            for item in raw_holdings
            if item.get("symbol") or item.get("code")
        }
        holdings.append(
            HoldingSnapshot(
                as_of=as_of,
                weights=weights,
                exposures={"gross": sum(abs(weight) for weight in weights.values())},
            )
        )

    trades = [
        TradeRecord(
            traded_at=str(item.get("time") or item.get("date") or ""),
            symbol=_canonical_symbol(item.get("symbol") or item.get("code")),
            side=str(item.get("side") or "").upper(),
            quantity=_number(item, "qty", _number(item, "shares")),
            price=_number(item, "price"),
            commission=_number(item, "fee"),
            slippage=0.0,
            reason="legacy_custom_engine",
        )
        for item in payload.get("trades", [])
    ]

    merged_diagnostics = {
        "bridge": "desktop_custom_engine",
        "legacy_payload_counts": {
            "nav": len(payload.get("nav", [])),
            "holdings": len(raw_holdings),
            "trades": len(payload.get("trades", [])),
        },
        "accounting": accounting,
    }
    if diagnostics:
        merged_diagnostics.update(diagnostics)

    return BacktestResult(
        run_id=request.run_id,
        status="completed",
        engine="chenxi_engine",
        strategy_id=request.strategy_id,
        strategy_version=request.strategy_version,
        benchmark=request.benchmark,
        metrics=metrics,
        equity_curve=equity_curve,
        trades=trades,
        holdings=holdings,
        diagnostics=merged_diagnostics,
    )
