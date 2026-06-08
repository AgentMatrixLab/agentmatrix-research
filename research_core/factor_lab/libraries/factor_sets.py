from __future__ import annotations

import pandas as pd

from research_core.factor_lab.libraries.alpha101 import IMPLEMENTED_ALPHA101_FACTORS, alpha101_specs, compute_alpha101_factors
from research_core.factor_lab.libraries.gtja191 import IMPLEMENTED_GTJA191_FACTORS, compute_gtja191_alphas, gtja191_specs


WQ101_ALPHA_1_10 = tuple(f"alpha{i}" for i in range(1, 11))


def compute_wq101_alphas(df: pd.DataFrame, factor_names: list[str] | None = None) -> pd.DataFrame:
    requested = list(factor_names or WQ101_ALPHA_1_10)
    invalid = [name for name in requested if name not in WQ101_ALPHA_1_10]
    if invalid:
        raise ValueError(f"Unsupported WQ101 Alpha101 1-10 factors: {invalid}")
    return compute_alpha101_factors(df, factor_names=requested)


def compute_factor_set(df: pd.DataFrame, factor_set: str, factor_names: list[str] | None = None) -> pd.DataFrame:
    normalized = factor_set.lower()
    if normalized in {"wq101", "alpha101"}:
        return compute_wq101_alphas(df, factor_names=factor_names)
    if normalized in {"gtja191", "alpha191"}:
        return compute_gtja191_alphas(df, factor_names=factor_names)
    raise ValueError(f"Unsupported factor_set: {factor_set}")


def factor_set_specs(factor_set: str):
    normalized = factor_set.lower()
    if normalized in {"wq101", "alpha101"}:
        return [spec for spec in alpha101_specs() if spec.factor_name in WQ101_ALPHA_1_10]
    if normalized in {"gtja191", "alpha191"}:
        return gtja191_specs()
    raise ValueError(f"Unsupported factor_set: {factor_set}")


def factor_set_library_name(factor_set: str) -> str:
    normalized = factor_set.lower()
    if normalized in {"wq101", "alpha101"}:
        return "Alpha101"
    if normalized in {"gtja191", "alpha191"}:
        return "GTJA191"
    raise ValueError(f"Unsupported factor_set: {factor_set}")


__all__ = [
    "IMPLEMENTED_ALPHA101_FACTORS",
    "IMPLEMENTED_GTJA191_FACTORS",
    "WQ101_ALPHA_1_10",
    "compute_factor_set",
    "compute_gtja191_alphas",
    "compute_wq101_alphas",
    "factor_set_library_name",
    "factor_set_specs",
]
