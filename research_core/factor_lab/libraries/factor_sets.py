from __future__ import annotations

import pandas as pd

from research_core.factor_lab.libraries.alpha101 import IMPLEMENTED_ALPHA101_FACTORS, alpha101_specs, compute_alpha101_factors
from research_core.factor_lab.libraries.alpha158 import compute_alpha158 as _compute_alpha158, get_factor_names as _alpha158_names
from research_core.factor_lab.libraries.gtja191 import IMPLEMENTED_GTJA191_FACTORS, compute_gtja191_alphas, gtja191_specs


WQ101_ALPHA_1_10 = tuple(f"alpha{i}" for i in range(1, 11))
IMPLEMENTED_ALPHA158_FACTORS = tuple(_alpha158_names())
ALPHA158_ALL_FACTORS = IMPLEMENTED_ALPHA158_FACTORS


def compute_wq101_alphas(df: pd.DataFrame, factor_names: list[str] | None = None) -> pd.DataFrame:
    requested = list(factor_names or IMPLEMENTED_ALPHA101_FACTORS)
    invalid = [name for name in requested if name not in IMPLEMENTED_ALPHA101_FACTORS]
    if invalid:
        raise ValueError(f"Unsupported WQ101 Alpha101 factors: {invalid}")
    return compute_alpha101_factors(df, factor_names=requested)


def compute_alpha158_alphas(df: pd.DataFrame, factor_names: list[str] | None = None) -> pd.DataFrame:
    """Compute Alpha158 factors from a panel DataFrame (date, code, open, high, low, close, volume, [vwap|amount]).

    Converts the flat panel to MultiIndex format expected by compute_alpha158().
    If vwap is missing, approximates it as amount / volume.
    """
    panel = df.copy()
    if "vwap" not in panel.columns:
        if "amount" in panel.columns and "volume" in panel.columns:
            panel["vwap"] = panel["amount"] / panel["volume"].replace(0, pd.NA)
        else:
            panel["vwap"] = panel["close"]

    multi_df = panel.set_index(["date", "code"])
    multi_df.index = multi_df.index.set_names(["datetime", "instrument"])
    for col in ["open", "high", "low", "close", "vwap", "volume"]:
        if col not in multi_df.columns:
            raise ValueError(f"Alpha158 requires column '{col}' in input data")

    result = _compute_alpha158(multi_df[["open", "high", "low", "close", "vwap", "volume"]])
    result = result.reset_index()
    result = result.rename(columns={"datetime": "date", "instrument": "code"})

    if factor_names is not None:
        requested = list(factor_names)
        invalid = [name for name in requested if name not in result.columns]
        if invalid:
            raise ValueError(f"Unsupported Alpha158 factors: {invalid}")
        return result[["date", "code"] + requested]

    return result


def compute_factor_set(df: pd.DataFrame, factor_set: str, factor_names: list[str] | None = None) -> pd.DataFrame:
    normalized = factor_set.lower()
    if normalized in {"wq101", "alpha101"}:
        return compute_wq101_alphas(df, factor_names=factor_names)
    if normalized in {"gtja191", "alpha191"}:
        return compute_gtja191_alphas(df, factor_names=factor_names)
    if normalized in {"alpha158"}:
        return compute_alpha158_alphas(df, factor_names=factor_names)
    raise ValueError(f"Unsupported factor_set: {factor_set}")


def factor_set_specs(factor_set: str):
    normalized = factor_set.lower()
    if normalized in {"wq101", "alpha101"}:
        return [spec for spec in alpha101_specs() if spec.factor_name in IMPLEMENTED_ALPHA101_FACTORS]
    if normalized in {"gtja191", "alpha191"}:
        return gtja191_specs()
    if normalized in {"alpha158"}:
        from research_core.factor_lab.libraries.alpha158.specs import FACTOR_SPECS
        from contracts.factor_research import FactorResearchSpec
        return [
            FactorResearchSpec(
                factor_name=name,
                display_name=name,
                library="Alpha158",
                factor_id=f"alpha158_{name.lower()}",
                version="1.0.0",
                frequency="daily",
                required_fields=["open", "high", "low", "close", "volume", "vwap"],
                formula=desc,
                metadata={"status": "implemented", "implementation_stage": "verified"},
                tags=["alpha158", "qlib"],
            )
            for name, desc in FACTOR_SPECS.items()
        ]
    raise ValueError(f"Unsupported factor_set: {factor_set}")


def factor_set_library_name(factor_set: str) -> str:
    normalized = factor_set.lower()
    if normalized in {"wq101", "alpha101"}:
        return "Alpha101"
    if normalized in {"gtja191", "alpha191"}:
        return "GTJA191"
    if normalized in {"alpha158"}:
        return "Alpha158"
    raise ValueError(f"Unsupported factor_set: {factor_set}")


__all__ = [
    "ALPHA158_ALL_FACTORS",
    "IMPLEMENTED_ALPHA101_FACTORS",
    "IMPLEMENTED_ALPHA158_FACTORS",
    "IMPLEMENTED_GTJA191_FACTORS",
    "WQ101_ALPHA_1_10",
    "compute_alpha158_alphas",
    "compute_factor_set",
    "compute_gtja191_alphas",
    "compute_wq101_alphas",
    "factor_set_library_name",
    "factor_set_specs",
]
