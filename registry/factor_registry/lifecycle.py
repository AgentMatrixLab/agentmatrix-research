from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from contracts.factor_research import FACTOR_LIFECYCLE_STATES, FactorPromotionRecord
from research_core.factor_lab.runtime import now_iso


ALLOWED_TRANSITIONS = {
    "candidate": {"implemented"},
    "implemented": {"internal_validated"},
    "internal_validated": {"strategy_candidate"},
    "strategy_candidate": {"external_sim_ready"},
    "external_sim_ready": {"external_sim_passed"},
    "external_sim_passed": {"live_ready"},
    "live_ready": {"live_approved"},
    "live_approved": set(),
}


def validate_lifecycle_state(state: str) -> str:
    if state not in FACTOR_LIFECYCLE_STATES:
        raise ValueError(f"Unknown factor lifecycle state: {state}")
    return state


def validate_transition(from_state: str, to_state: str) -> None:
    validate_lifecycle_state(from_state)
    validate_lifecycle_state(to_state)
    if to_state not in ALLOWED_TRANSITIONS[from_state]:
        raise ValueError(f"Invalid factor lifecycle transition: {from_state} -> {to_state}")


def build_promotion_record(
    *,
    factor_name: str,
    from_state: str,
    to_state: str,
    promoted_by: str,
    run_id: str = "",
    reason: str = "",
    evidence: dict[str, str] | None = None,
    approvals: list[str] | None = None,
    diagnostics: dict[str, Any] | None = None,
) -> FactorPromotionRecord:
    validate_transition(from_state, to_state)
    if to_state in {"live_ready", "live_approved"} and not approvals:
        raise ValueError("live_ready and live_approved promotions require explicit approvals")
    return FactorPromotionRecord(
        factor_name=factor_name,
        from_state=from_state,
        to_state=to_state,
        promoted_by=promoted_by,
        promoted_at=now_iso(),
        run_id=run_id,
        reason=reason,
        evidence=evidence or {},
        approvals=approvals or [],
        diagnostics=diagnostics or {},
    )


def append_promotion_record(path: str | Path, record: FactorPromotionRecord) -> str:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")
    return str(output_path)
