from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class FactorDefinition:
    factor_id: str
    name: str
    expression: str
    description: str = ""
    source: str = "manual"
    author: str = "unknown"
    tags: list[str] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class FactorMetric:
    name: str
    value: float
    higher_is_better: bool = True


@dataclass(slots=True)
class FactorEvaluation:
    factor_id: str
    score_horizon: int
    coverage: int
    metrics: list[FactorMetric] = field(default_factory=list)
    artifacts: dict[str, str] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class FactorMiningCandidate:
    name: str
    expression: str
    description: str = ""
    rationale: str = ""
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
