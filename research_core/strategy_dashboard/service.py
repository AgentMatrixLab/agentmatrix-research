from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from common.paths import runtime_path


class StrategyResultNotFound(KeyError):
    pass


class StrategyDashboardStore:
    """Read-only view over persisted AgentMatrix BacktestResult JSON files."""

    def __init__(self, result_dir: str | Path | None = None, publication_status: str = "published"):
        self.result_dir = Path(result_dir) if result_dir else runtime_path("custom_engine", "backtests")
        self.publication_status = publication_status

    def _payloads(self) -> list[tuple[Path, dict[str, Any]]]:
        if not self.result_dir.is_dir():
            return []
        payloads = []
        for path in sorted(self.result_dir.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if payload.get("status") != "completed":
                continue
            payloads.append((path, payload))
        return payloads

    def list_strategies(self) -> list[dict[str, Any]]:
        latest_by_strategy: dict[str, tuple[Path, dict[str, Any]]] = {}
        run_counts: dict[str, int] = {}
        for path, payload in self._payloads():
            strategy_id = str(payload.get("strategy_id") or "")
            if strategy_id:
                run_counts[strategy_id] = run_counts.get(strategy_id, 0) + 1
            if strategy_id and strategy_id not in latest_by_strategy:
                latest_by_strategy[strategy_id] = (path, payload)
        items = [
            {**self._summary(path, payload), "run_count": run_counts[strategy_id]}
            for strategy_id, (path, payload) in latest_by_strategy.items()
        ]
        items.sort(key=lambda item: (item["sharpe"], item["annualized_return"]), reverse=True)
        for rank, item in enumerate(items, 1):
            item["rank"] = rank
        return items

    def get_strategy(self, strategy_id: str) -> dict[str, Any]:
        for path, payload in self._payloads():
            if payload.get("strategy_id") == strategy_id:
                return self._detail(path, payload)
        raise StrategyResultNotFound(strategy_id)

    @staticmethod
    def _display_name(payload: dict[str, Any]) -> str:
        diagnostics = payload.get("diagnostics") or {}
        return str(diagnostics.get("strategy_name") or payload.get("strategy_id") or "未命名策略")

    def _summary(self, path: Path, payload: dict[str, Any]) -> dict[str, Any]:
        metrics = payload.get("metrics") or {}
        curve = payload.get("equity_curve") or []
        diagnostics = payload.get("diagnostics") or {}
        quality = diagnostics.get("quality") or {}
        return {
            "id": payload.get("strategy_id"),
            "name": self._display_name(payload),
            "version": payload.get("strategy_version"),
            "engine": payload.get("engine"),
            "run_id": payload.get("run_id"),
            "status": payload.get("status"),
            "publication_status": diagnostics.get("publication_status") or self.publication_status,
            "quality_status": "passed" if quality.get("passed") is True else "unverified",
            "data_version": diagnostics.get("data_version"),
            "start_date": curve[0].get("timestamp") if curve else None,
            "end_date": curve[-1].get("timestamp") if curve else None,
            "total_return": metrics.get("total_return", 0.0),
            "annualized_return": metrics.get("annualized_return", 0.0),
            "sharpe": metrics.get("sharpe", 0.0),
            "max_drawdown": metrics.get("max_drawdown", 0.0),
            "updated_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
        }

    def _detail(self, path: Path, payload: dict[str, Any]) -> dict[str, Any]:
        summary = self._summary(path, payload)
        curve = [
            {
                "date": point.get("timestamp"),
                "nav": point.get("strategy_nav", 1.0),
                "benchmark": point.get("benchmark_nav", 1.0),
                "drawdown": point.get("drawdown", 0.0),
            }
            for point in payload.get("equity_curve", [])
        ]
        snapshots = payload.get("holdings") or []
        latest = snapshots[-1] if snapshots else {"as_of": None, "weights": {}, "exposures": {}}
        positions = [
            {"symbol": symbol, "weight": weight}
            for symbol, weight in sorted((latest.get("weights") or {}).items(), key=lambda item: abs(item[1]), reverse=True)
        ]
        trades = []
        for item in payload.get("trades", []):
            quantity = float(item.get("quantity") or 0.0)
            price = float(item.get("price") or 0.0)
            trades.append(
                {
                    "time": item.get("traded_at"),
                    "symbol": item.get("symbol"),
                    "side": str(item.get("side") or "").upper(),
                    "quantity": quantity,
                    "price": price,
                    "amount": quantity * price,
                    "commission": float(item.get("commission") or 0.0),
                    "slippage": float(item.get("slippage") or 0.0),
                }
            )
        return {
            **summary,
            "benchmark": payload.get("benchmark"),
            "metrics": payload.get("metrics") or {},
            "equity_curve": curve,
            "positions_as_of": latest.get("as_of"),
            "gross_exposure": (latest.get("exposures") or {}).get("gross", sum(abs(p["weight"]) for p in positions)),
            "positions": positions,
            "trades": trades,
            "diagnostics": payload.get("diagnostics") or {},
        }
