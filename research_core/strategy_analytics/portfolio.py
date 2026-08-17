from __future__ import annotations

from datetime import datetime
from typing import Any

from research_core.strategy_analytics.performance import analyze_window


def _rebalance_key(date: str, frequency: str) -> tuple[int, ...]:
    value = datetime.fromisoformat(date[:10])
    if frequency == "daily":
        return value.year, value.month, value.day
    if frequency == "weekly":
        iso = value.isocalendar()
        return iso.year, iso.week
    if frequency == "quarterly":
        return value.year, (value.month - 1) // 3
    return value.year, value.month


def combine_portfolio(
    series: list[tuple[float, list[dict[str, Any]]]],
    rebalance: str = "monthly",
    *,
    initial_cash: float = 1_000_000.0,
    commission_bps: float = 3.0,
    slippage_bps: float = 5.0,
) -> dict[str, Any]:
    """Backtest strategy sleeves through one shared cash/position ledger.

    Each strategy NAV is treated as a tradable sleeve. Rebalancing exchanges
    sleeve units using closing NAV and charges two-sided execution costs.
    """
    if len(series) < 2:
        raise ValueError("at least two strategies are required")
    if abs(sum(weight for weight, _ in series) - 1) > 1e-6:
        raise ValueError("weights must sum to one")
    if rebalance not in {"daily", "weekly", "monthly", "quarterly"}:
        raise ValueError("unsupported rebalance frequency")
    maps = [{point["date"]: point for point in curve} for _, curve in series]
    dates = sorted(set.intersection(*(set(mapping) for mapping in maps)))
    if len(dates) < 2:
        raise ValueError("no common NAV window")

    prices = [[float(mapping[date]["nav"]) for date in dates] for mapping in maps]
    benchmark_bases = [float(mapping[dates[0]].get("benchmark") or 1) for mapping in maps]
    units = [0.0] * len(series)
    cash = float(initial_cash)
    cost_rate = (commission_bps + slippage_bps) / 10_000
    trades: list[dict[str, Any]] = []
    curve: list[dict[str, Any]] = []
    last_key: tuple[int, ...] | None = None
    peak = initial_cash

    for day_index, date in enumerate(dates):
        current_prices = [row[day_index] for row in prices]
        equity_before = cash + sum(units[i] * current_prices[i] for i in range(len(series)))
        key = _rebalance_key(date, rebalance)
        should_rebalance = day_index == 0 or key != last_key
        if should_rebalance:
            # Sell overweight sleeves first so buys share the same settled cash.
            targets = [equity_before * weight for weight, _ in series]
            deltas = [targets[i] - units[i] * current_prices[i] for i in range(len(series))]
            for side in (-1, 1):
                for i, delta in enumerate(deltas):
                    if delta * side <= 0:
                        continue
                    notional = abs(delta)
                    if delta > 0:
                        notional = min(notional, max(cash, 0.0) / (1 + cost_rate))
                        delta = notional
                    fee = notional * cost_rate
                    unit_delta = delta / current_prices[i]
                    units[i] += unit_delta
                    cash -= delta + fee
                    trades.append({"date": date, "sleeve": i, "side": "BUY" if delta > 0 else "SELL", "notional": notional, "cost": fee})
            last_key = key
        equity = cash + sum(units[i] * current_prices[i] for i in range(len(series)))
        peak = max(peak, equity)
        benchmark = sum(
            series[i][0] * float(maps[i][date].get("benchmark") or benchmark_bases[i]) / benchmark_bases[i]
            for i in range(len(series))
        )
        curve.append({"date": date, "nav": equity / initial_cash, "benchmark": benchmark, "drawdown": equity / peak - 1})

    return {
        "methodology": "shared_cash_sleeve_ledger_v1",
        "rebalance": rebalance,
        "initial_cash": initial_cash,
        "ending_cash": cash,
        "execution_cost": sum(item["cost"] for item in trades),
        "trades": trades,
        "curve": curve,
        "metrics": analyze_window(curve),
    }
