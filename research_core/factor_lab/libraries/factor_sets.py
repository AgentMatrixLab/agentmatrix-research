from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd

from research_core.factor_lab.libraries.alpha101 import IMPLEMENTED_ALPHA101_FACTORS, alpha101_specs, compute_alpha101_factors
from research_core.factor_lab.libraries.gtja191 import IMPLEMENTED_GTJA191_FACTORS, compute_gtja191_alphas, gtja191_specs


WQ101_ALPHA_1_101 = tuple(f"alpha{i}" for i in range(1, 102))


def compute_wq101_alphas(df: pd.DataFrame, factor_names: list[str] | None = None) -> pd.DataFrame:
    requested = list(factor_names or WQ101_ALPHA_1_101)
    invalid = [name for name in requested if name not in WQ101_ALPHA_1_101]
    if invalid:
        raise ValueError(f"Unsupported WQ101 Alpha101 1-10 factors: {invalid}")
    return compute_alpha101_factors(df, factor_names=requested)


# ---- Custom/uploaded factor support ----

UPLOADS_DIR = Path(__file__).resolve().parents[3] / "runtime" / "factor_lab" / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


def _load_uploaded_factor(name: str):
    """Dynamically load a user-uploaded factor from uploads/<name>.py."""
    path = UPLOADS_DIR / f"{name}.py"
    if not path.exists():
        raise ValueError(f"Uploaded factor '{name}' not found at {path}")
    spec = importlib.util.spec_from_file_location(f"custom_factor_{name}", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    if not hasattr(mod, "compute"):
        raise ValueError(f"Factor '{name}' must define a compute(df) -> pd.Series function")
    return mod.compute


def _list_uploaded_factors() -> list[str]:
    if not UPLOADS_DIR.exists():
        return []
    return sorted([p.stem for p in UPLOADS_DIR.glob("*.py")])


def compute_custom_factors(df: pd.DataFrame, factor_names: list[str] | None = None) -> pd.DataFrame:
    requested = list(factor_names or _list_uploaded_factors())
    invalid = [n for n in requested if not (UPLOADS_DIR / f"{n}.py").exists()]
    if invalid:
        raise ValueError(f"Uploaded factors not found: {invalid}")
    import numpy as np

    result = df[["date", "code"]].copy()
    for name in requested:
        func = _load_uploaded_factor(name)
        result[name] = func(df)
    return result


def custom_specs() -> list:
    from contracts.factor_research import FactorResearchSpec, ValidationThreshold

    specs = []
    for name in _list_uploaded_factors():
        specs.append(
            FactorResearchSpec(
                factor_name=name,
                library="Custom",
                version="v1.0",
                display_name=name,
                factor_id=f"custom_{name}",
                source_document="User uploaded",
                frequency="day",
                required_fields=["open", "high", "low", "close", "volume"],
                metadata={"status": "implemented", "implementation_stage": "code"},
            )
        )
    return specs


# ---- End custom support ----


def compute_factor_set(df: pd.DataFrame, factor_set: str, factor_names: list[str] | None = None) -> pd.DataFrame:
    normalized = factor_set.lower()
    if normalized in {"wq101", "alpha101"}:
        return compute_wq101_alphas(df, factor_names=factor_names)
    if normalized in {"gtja191", "alpha191"}:
        return compute_gtja191_alphas(df, factor_names=factor_names)
    if normalized == "custom":
        return compute_custom_factors(df, factor_names=factor_names)
    raise ValueError(f"Unsupported factor_set: {factor_set}")


def factor_set_specs(factor_set: str):
    normalized = factor_set.lower()
    if normalized in {"wq101", "alpha101"}:
        return [spec for spec in alpha101_specs() if spec.factor_name in WQ101_ALPHA_1_101]
    if normalized in {"gtja191", "alpha191"}:
        return gtja191_specs()
    if normalized == "custom":
        return custom_specs()
    raise ValueError(f"Unsupported factor_set: {factor_set}")


def factor_set_library_name(factor_set: str) -> str:
    normalized = factor_set.lower()
    if normalized in {"wq101", "alpha101"}:
        return "Alpha101"
    if normalized in {"gtja191", "alpha191"}:
        return "GTJA191"
    if normalized == "custom":
        return "Custom"
    raise ValueError(f"Unsupported factor_set: {factor_set}")


__all__ = [
    "IMPLEMENTED_ALPHA101_FACTORS",
    "IMPLEMENTED_GTJA191_FACTORS",
    "WQ101_ALPHA_1_101",
    "compute_factor_set",
    "compute_gtja191_alphas",
    "compute_wq101_alphas",
    "factor_set_library_name",
    "factor_set_specs",
]
