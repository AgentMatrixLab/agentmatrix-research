from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


FACTOR_LIFECYCLE_STATES = [
    "candidate",
    "implemented",
    "internal_validated",
    "strategy_candidate",
    "external_sim_ready",
    "external_sim_passed",
    "live_ready",
    "live_approved",
]


@dataclass(slots=True)
class DataSourceSpec:
    name: str
    kind: str
    description: str = ""
    config_path: str = ""
    readonly: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PanelRequest:
    data_source: str
    start: str
    end: str
    universe: str = "csi800"
    symbols: list[str] = field(default_factory=list)
    fields: list[str] = field(default_factory=list)
    filters: dict[str, Any] = field(default_factory=dict)
    warmup_calendar_days: int = 420
    max_symbols: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class DataQualityIssue:
    severity: str
    check: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class DataQualityReport:
    source: str
    status: str
    row_count: int
    date_min: str = ""
    date_max: str = ""
    n_codes: int = 0
    duplicate_count: int = 0
    coverage: dict[str, float] = field(default_factory=dict)
    issues: list[DataQualityIssue] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PanelSnapshot:
    request: PanelRequest
    source: DataSourceSpec
    quality: DataQualityReport
    panel_path: str = ""
    rows: int = 0
    n_codes: int = 0
    n_dates: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


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


@dataclass(slots=True)
class FactorValidationRun:
    run_id: str
    factor_names: list[str]
    library: str
    panel: PanelSnapshot
    validation_config: dict[str, Any] = field(default_factory=dict)
    generated_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class FactorValidationResult:
    run_id: str
    factor_name: str
    lifecycle_state: str
    status: str
    metrics: dict[str, Any] = field(default_factory=dict)
    red_flags: list[dict[str, Any]] = field(default_factory=list)
    artifacts: dict[str, str] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class FactorPromotionRecord:
    factor_name: str
    from_state: str
    to_state: str
    promoted_by: str
    promoted_at: str
    run_id: str = ""
    reason: str = ""
    evidence: dict[str, str] = field(default_factory=dict)
    approvals: list[str] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)
