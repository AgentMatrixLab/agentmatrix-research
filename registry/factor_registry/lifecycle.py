"""
Factor lifecycle state machine.

Enables factor status transitions: draft → evaluating → passed →
registered → retired, with rejected and monitoring states.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum


class FactorStatus(str, Enum):
    DRAFT = "draft"
    EVALUATING = "evaluating"
    PASSED = "passed"
    REGISTERED = "registered"
    RETIRED = "retired"
    REJECTED = "rejected"
    MONITORING = "monitoring"


_VALID_TRANSITIONS: dict[FactorStatus, set[FactorStatus]] = {
    FactorStatus.DRAFT: {FactorStatus.EVALUATING},
    FactorStatus.EVALUATING: {FactorStatus.PASSED, FactorStatus.REJECTED},
    FactorStatus.PASSED: {FactorStatus.REGISTERED, FactorStatus.EVALUATING},
    FactorStatus.REGISTERED: {FactorStatus.RETIRED, FactorStatus.MONITORING},
    FactorStatus.RETIRED: {FactorStatus.EVALUATING},
    FactorStatus.REJECTED: {FactorStatus.EVALUATING},
    FactorStatus.MONITORING: {FactorStatus.RETIRED, FactorStatus.REGISTERED},
}

ALLOWED_TRANSITIONS = _VALID_TRANSITIONS


def can_transition(current: FactorStatus, target: FactorStatus) -> bool:
    """Check if a status transition is valid."""
    return target in _VALID_TRANSITIONS.get(current, set())


def allowed_targets(current: FactorStatus) -> set[FactorStatus]:
    """Get allowed next states from current status."""
    return _VALID_TRANSITIONS.get(current, set())


def validate_transition(current: str, target: str) -> bool:
    """Validate a factor status transition from string inputs."""
    try:
        return can_transition(FactorStatus(current), FactorStatus(target))
    except ValueError:
        return False


def validate_lifecycle_state(factor: dict) -> bool:
    """Validate a factor's lifecycle state field."""
    status = factor.get("status", "draft")
    try:
        FactorStatus(status)
        return True
    except ValueError:
        return False


def build_promotion_record(factor_name: str, from_status: str, to_status: str) -> dict:
    """Build a promotion record for factor lifecycle tracking."""
    return {
        "factor_name": factor_name,
        "from_status": from_status,
        "to_status": to_status,
        "timestamp": datetime.utcnow().isoformat(),
    }


def append_promotion_record(factor: dict, record: dict) -> dict:
    """Append a promotion record to a factor's history."""
    factor = dict(factor)
    history = factor.get("promotion_history", [])
    history.append(record)
    factor["promotion_history"] = history
    return factor
