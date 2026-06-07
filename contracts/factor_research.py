from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ValidationThreshold:
    metric: str
    operator: str
    value: float
    description: str = ""


@dataclass(slots=True)
class FactorResearchSpec:
    factor_name: str
    library: str
    version: str
    display_name: str = ""
    factor_id: str = ""
    source_document: str = ""
    formula: str = ""
    description: str = ""
    frequency: str = "day"
    sample_scope: str = ""
    required_fields: list[str] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)
    preprocessing: list[str] = field(default_factory=list)
    neutralization: list[str] = field(default_factory=list)
    validation_targets: list[ValidationThreshold] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class FactorValidationArtifact:
    artifact_type: str
    path: str
    description: str = ""


@dataclass(slots=True)
class FactorValidationReport:
    factor_name: str
    library: str
    status: str
    summary: str = ""
    checks: list[dict[str, Any]] = field(default_factory=list)
    artifacts: list[FactorValidationArtifact] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)
