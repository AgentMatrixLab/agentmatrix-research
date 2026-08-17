"""Stratification result cache — prevents redundant recomputation."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

def _sanitize_nan(obj):
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize_nan(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_nan(v) for v in obj]
    return obj

from research_core.factor_lab.runtime import FactorLabWorkspaceConfig, now_iso


def _config_hash(payload: dict[str, Any]) -> str:
    """Deterministic hash of research configuration (ignores non-semantic keys)."""
    sig = {
        "factor_name": payload.get("factor_name"),
        "factor_set": payload.get("factor_set"),
        "data_source": payload.get("data_source"),
        "n_groups": payload.get("n_groups"),
        "n_symbols": payload.get("n_symbols"),
        "n_dates": payload.get("n_dates"),
    }
    raw = json.dumps(sig, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def save_cached_result(
    config: FactorLabWorkspaceConfig,
    library: str,
    factor_name: str,
    payload: dict[str, Any],
    result: dict[str, Any],
) -> None:
    """Persist stratification result and its config metadata."""
    results_dir = config.results_path(library, factor_name)
    results_dir.mkdir(parents=True, exist_ok=True)

    meta = {
        "factor_name": factor_name,
        "library": library,
        "factor_set": payload.get("factor_set"),
        "data_source": payload.get("data_source"),
        "n_groups": payload.get("n_groups"),
        "n_symbols": payload.get("n_symbols"),
        "n_dates": payload.get("n_dates"),
        "config_hash": _config_hash(payload),
        "version": 1,
        "created_at": now_iso(),
    }

    meta_path = results_dir / "meta.json"
    data_path = results_dir / "stratification.json"

    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    data_path.write_text(json.dumps(_sanitize_nan(result), ensure_ascii=False, default=str), encoding="utf-8")


def load_cached_result(
    config: FactorLabWorkspaceConfig,
    library: str,
    factor_name: str,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    """Return cached stratification result if config matches, else None."""
    meta_path = config.results_meta_path(library, factor_name)
    data_path = config.results_data_path(library, factor_name)

    if not meta_path.exists() or not data_path.exists():
        return None

    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, KeyError):
        return None

    current_hash = _config_hash(payload)
    if meta.get("config_hash") != current_hash:
        return None  # config changed → recompute

    try:
        return json.loads(data_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError):
        return None


def invalidate_cache(
    config: FactorLabWorkspaceConfig,
    library: str,
    factor_name: str,
) -> None:
    """Delete cached results for a factor."""
    import shutil
    results_dir = config.results_path(library, factor_name)
    if results_dir.exists():
        shutil.rmtree(results_dir)
