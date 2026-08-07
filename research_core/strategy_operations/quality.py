from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from contracts.backtest import BacktestResult


@dataclass(frozen=True, slots=True)
class QualityReport:
    passed: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]


def validate_result(
    result: BacktestResult,
    *,
    expected_end_date: str,
    gates: dict[str, Any] | None = None,
) -> QualityReport:
    gates = gates or {}
    errors: list[str] = []
    warnings: list[str] = []
    if result.status != "completed":
        errors.append(f"run status is {result.status!r}, expected 'completed'")
    if not result.equity_curve:
        errors.append("equity curve is empty")
    else:
        dates = [point.timestamp[:10] for point in result.equity_curve]
        if dates != sorted(dates) or len(dates) != len(set(dates)):
            errors.append("equity curve dates are not strictly increasing")
        if dates[-1] < expected_end_date:
            errors.append(f"result ends at {dates[-1]}, before data version {expected_end_date}")
        for point in result.equity_curve:
            if not all(math.isfinite(value) for value in (point.strategy_nav, point.benchmark_nav, point.drawdown)):
                errors.append("equity curve contains non-finite values")
                break
            if point.strategy_nav <= 0 or point.benchmark_nav <= 0:
                errors.append("equity curve contains non-positive NAV")
                break
    metric_values = vars(result.metrics) if hasattr(result.metrics, "__dict__") else {
        field: getattr(result.metrics, field) for field in result.metrics.__slots__
    }
    if not all(math.isfinite(float(value)) for value in metric_values.values()):
        errors.append("metrics contain non-finite values")
    max_gross = float(gates.get("max_gross_exposure", 1.05))
    for snapshot in result.holdings:
        gross = float(snapshot.exposures.get("gross", sum(abs(v) for v in snapshot.weights.values())))
        if gross > max_gross:
            errors.append(f"gross exposure {gross:.4f} exceeds {max_gross:.4f} at {snapshot.as_of}")
            break
    minimum_trades = int(gates.get("min_trade_count", 0))
    if len(result.trades) < minimum_trades:
        errors.append(f"trade count {len(result.trades)} is below minimum {minimum_trades}")
    if gates.get("require_holdings") and not result.holdings:
        errors.append("holding history is empty")
    if gates.get("require_nav_movement") and result.equity_curve:
        nav_values = [point.strategy_nav for point in result.equity_curve]
        if max(nav_values) - min(nav_values) <= 1e-12:
            errors.append("strategy NAV is flat")
    sides = {trade.side.upper() for trade in result.trades}
    if gates.get("require_two_sided_trades") and not {"BUY", "SELL"}.issubset(sides):
        errors.append("trade history does not contain both BUY and SELL records")
    if result.trades and float(result.metrics.turnover) == 0:
        message = "turnover is zero despite non-empty trade history"
        if gates.get("require_positive_turnover"):
            errors.append(message)
        else:
            warnings.append(message)
    return QualityReport(not errors, tuple(errors), tuple(warnings))
