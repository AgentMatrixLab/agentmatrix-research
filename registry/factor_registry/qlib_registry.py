from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from common.paths import runtime_path
from contracts.factor import FactorDefinition


REGISTRY_FILE = runtime_path("qlib", "factor_registry.json")


def _now_iso() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_registry() -> list[dict]:
    if not REGISTRY_FILE.exists():
        return []
    return json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))


def _save_registry(entries: list[dict]) -> None:
    REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_FILE.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


def save_factor_definition(factor: FactorDefinition) -> dict:
    payload = asdict(factor)
    payload.setdefault("created_at", _now_iso())
    payload["updated_at"] = _now_iso()

    entries = _load_registry()
    replaced = False
    for idx, entry in enumerate(entries):
        if entry["factor_id"] == factor.factor_id:
            payload["created_at"] = entry.get("created_at", payload["created_at"])
            entries[idx] = payload
            replaced = True
            break
    if not replaced:
        entries.append(payload)
    _save_registry(entries)
    return payload


def get_factor_definition(factor_id: str) -> dict | None:
    for entry in _load_registry():
        if entry["factor_id"] == factor_id:
            return entry
    return None


def list_factor_definitions() -> list[dict]:
    return _load_registry()
