from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


ALLOWED_STATUSES = {"draft", "review", "approved", "published", "disabled"}


@dataclass(frozen=True, slots=True)
class StrategyDefinition:
    strategy_id: str
    name: str
    version: str
    owner: str
    status: str
    engine: str
    benchmark: str
    start_date: str
    initial_cash: float
    commission_bps: float
    slippage_bps: float
    parameters: dict[str, Any] = field(default_factory=dict)
    quality_gates: dict[str, Any] = field(default_factory=dict)

    @property
    def runnable(self) -> bool:
        return self.status in {"approved", "published"}


def load_registry(path: str | Path) -> list[StrategyDefinition]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("Unsupported strategy registry schema_version")
    definitions = []
    seen = set()
    for raw in payload.get("strategies", []):
        definition = StrategyDefinition(**raw)
        if not definition.strategy_id or definition.strategy_id in seen:
            raise ValueError(f"Invalid or duplicate strategy_id: {definition.strategy_id!r}")
        if definition.status not in ALLOWED_STATUSES:
            raise ValueError(f"Invalid strategy status: {definition.status}")
        seen.add(definition.strategy_id)
        definitions.append(definition)
    return definitions
