from __future__ import annotations

from typing import Any

from contracts.backtest import (
    BacktestRequest,
    BacktestResult,
    EquityPoint,
    HoldingSnapshot,
    PerformanceMetrics,
    TradeRecord,
    PositionRecord,
)
from research_core.backtest_adapter.custom_engine.ledger import rebuild_position_ledger
from research_core.strategy_analytics.performance import analyze_window


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
            reason=str(item.get("reason") or "legacy_custom_engine"),
            sub_strategy=str(item.get("sub_strategy") or ""),
            realized_pnl=float(item["realized_pnl"]) if item.get("realized_pnl") is not None else None,
        )
        for item in payload.get("trades", [])
    ]
    ledger = rebuild_position_ledger(payload.get("trades", []), request.initial_cash, {
        str(item.get("symbol") or item.get("code") or ""): _number(item, "price", _number(item, "last_price"))
        for item in raw_holdings
    })
    ledger_positions = [PositionRecord(**{**row, "symbol": _canonical_symbol(row["symbol"])}) for row in ledger["positions"]]
    if not holdings and (ledger_positions or payload.get("trades")):
        holdings.append(HoldingSnapshot(
            as_of=str(payload.get("as_of") or (equity_curve[-1].timestamp if equity_curve else "")),
            weights={row.symbol: row.weight for row in ledger_positions},
            exposures={"gross": sum(abs(row.weight) for row in ledger_positions)},
        ))
    if holdings:
        holdings[0].cash = ledger["cash"]
        holdings[0].total_equity = ledger["total_equity"]
        holdings[0].positions = ledger_positions
    analytics = analyze_window([{"date":p.timestamp,"nav":p.strategy_nav,"benchmark":p.benchmark_nav,"drawdown":p.drawdown} for p in equity_curve])
    for key in ("sortino","calmar","downside_volatility","beta","alpha","information_ratio","tracking_error","var_95"):
        setattr(metrics,key,analytics.get(key))

    merged_diagnostics = {
        "bridge": "desktop_custom_engine",
        "legacy_payload_counts": {
            "nav": len(payload.get("nav", [])),
            "holdings": len(raw_holdings),
            "trades": len(payload.get("trades", [])),
        },
        "accounting": accounting,
        "ledger": {k:v for k,v in ledger.items() if k != "positions"},
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
