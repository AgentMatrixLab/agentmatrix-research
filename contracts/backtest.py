from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from contracts.attribution import AttributionReport


@dataclass(slots=True)
class BacktestRequest:
    run_id: str
    strategy_id: str
    strategy_version: str
    strategy_params: dict[str, Any]
    module_path: str
    start_time: str
    end_time: str
    benchmark: str
    initial_cash: float
    slippage_bps: float = 0.0
    commission_bps: float = 0.0
    execution_engine: str = "gm"
    dataset_id: str = ""
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PerformanceMetrics:
    total_return: float
    annualized_return: float
    benchmark_return: float
    excess_return: float
    max_drawdown: float
    sharpe: float
    volatility: float
    turnover: float = 0.0
    win_rate: float = 0.0


@dataclass(slots=True)
class EquityPoint:
    timestamp: str
    strategy_nav: float
    benchmark_nav: float
    drawdown: float = 0.0


@dataclass(slots=True)
class TradeRecord:
    traded_at: str
    symbol: str
    side: str
    quantity: float
    price: float
    commission: float = 0.0
    slippage: float = 0.0
    reason: str = ""


@dataclass(slots=True)
class HoldingSnapshot:
    as_of: str
    weights: dict[str, float] = field(default_factory=dict)
    exposures: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class BacktestResult:
    run_id: str
    status: str
    engine: str
    strategy_id: str
    strategy_version: str
    benchmark: str
    metrics: PerformanceMetrics
    equity_curve: list[EquityPoint] = field(default_factory=list)
    trades: list[TradeRecord] = field(default_factory=list)
    holdings: list[HoldingSnapshot] = field(default_factory=list)
    attribution: AttributionReport | None = None
    artifacts: dict[str, str] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ExternalSimulationRequest:
    run_id: str
    engine: str
    strategy_id: str
    strategy_version: str
    signal_path: str
    start_time: str
    end_time: str
    benchmark: str = ""
    initial_cash: float = 1_000_000.0
    slippage_bps: float = 0.0
    commission_bps: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ExternalSimulationPackage:
    request: ExternalSimulationRequest
    status: str
    package_dir: str
    artifacts: dict[str, str] = field(default_factory=dict)
    checklist: list[str] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ExternalSimulationResult:
    run_id: str
    engine: str
    status: str
    metrics: PerformanceMetrics | None = None
    source_path: str = ""
    artifacts: dict[str, str] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)
