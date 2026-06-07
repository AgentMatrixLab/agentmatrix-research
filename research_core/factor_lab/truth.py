from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from contracts.factor_research import FactorResearchSpec
from research_core.factor_lab.runtime import FactorLabWorkspaceConfig, now_iso


def _corr(left: pd.Series, right: pd.Series) -> float:
    aligned = pd.concat([left, right], axis=1).dropna()
    if len(aligned) < 2:
        return float("nan")
    left_values = aligned.iloc[:, 0].astype(float).to_numpy()
    right_values = aligned.iloc[:, 1].astype(float).to_numpy()
    left_centered = left_values - left_values.mean()
    right_centered = right_values - right_values.mean()
    left_norm = float(np.sqrt(np.square(left_centered).sum()))
    right_norm = float(np.sqrt(np.square(right_centered).sum()))
    if left_norm == 0.0 or right_norm == 0.0:
        return float("nan")
    return float((left_centered * right_centered).sum() / (left_norm * right_norm))


def _spearman_corr(left: pd.Series, right: pd.Series) -> float:
    aligned = pd.concat([left, right], axis=1).dropna()
    if len(aligned) < 2:
        return float("nan")
    left_rank = aligned.iloc[:, 0].rank(method="average")
    right_rank = aligned.iloc[:, 1].rank(method="average")
    return _corr(left_rank, right_rank)


def _to_float(value: float | int | np.floating[Any] | np.integer[Any]) -> float:
    return float(value) if pd.notna(value) else float("nan")


def load_truth_frame(
    truth_csv_path: str | Path,
    *,
    factor_names: list[str],
) -> pd.DataFrame:
    path = Path(truth_csv_path)
    truth_frame = pd.read_csv(path)
    required_columns = {"date", "code", *factor_names}
    missing = sorted(required_columns - set(truth_frame.columns))
    if missing:
        raise ValueError(f"Truth CSV missing required columns: {missing}")
    truth_frame["date"] = pd.to_datetime(truth_frame["date"])
    return truth_frame[["date", "code", *factor_names]].copy()


def summarize_truth_frame(
    truth_frame: pd.DataFrame,
    *,
    factor_names: list[str],
) -> dict[str, Any]:
    dates = pd.to_datetime(truth_frame["date"])
    coverage: dict[str, dict[str, float | int]] = {}
    for factor_name in factor_names:
        series = truth_frame[factor_name]
        coverage[factor_name] = {
            "non_null_count": int(series.notna().sum()),
            "coverage_ratio": _to_float(series.notna().mean()) if len(series) else float("nan"),
        }
    return {
        "rows": int(len(truth_frame)),
        "dates": int(dates.nunique()),
        "codes": int(truth_frame["code"].nunique()),
        "factor_count": len(factor_names),
        "factor_names": list(factor_names),
        "coverage": coverage,
    }


def validate_truth_frame(
    truth_frame: pd.DataFrame,
    *,
    factor_names: list[str],
    max_duplicate_samples: int = 12,
) -> dict[str, Any]:
    summary = summarize_truth_frame(truth_frame, factor_names=factor_names)
    duplicate_mask = truth_frame.duplicated(subset=["date", "code"], keep=False)
    duplicate_rows = truth_frame.loc[duplicate_mask, ["date", "code"]].copy()
    if not duplicate_rows.empty:
        duplicate_rows["date"] = pd.to_datetime(duplicate_rows["date"]).dt.strftime("%Y-%m-%d")
    duplicate_pairs = duplicate_rows.drop_duplicates().head(max_duplicate_samples).to_dict(orient="records")
    empty_factors = [
        factor_name
        for factor_name in factor_names
        if int(summary["coverage"][factor_name]["non_null_count"]) == 0
    ]
    return {
        "valid": bool(summary["rows"] > 0 and not duplicate_pairs and not empty_factors),
        "rows": summary["rows"],
        "dates": summary["dates"],
        "codes": summary["codes"],
        "factor_count": summary["factor_count"],
        "factor_names": summary["factor_names"],
        "coverage": summary["coverage"],
        "duplicate_key_count": int(duplicate_mask.sum()),
        "duplicate_key_samples": duplicate_pairs,
        "empty_factors": empty_factors,
    }


def compare_factor_to_truth(
    factor_frame: pd.DataFrame,
    truth_frame: pd.DataFrame,
    *,
    factor_name: str,
    tolerance: float = 1e-12,
    max_mismatches: int = 12,
) -> dict[str, Any]:
    merged = factor_frame[["date", "code", factor_name]].merge(
        truth_frame[["date", "code", factor_name]].rename(columns={factor_name: "truth_value"}),
        on=["date", "code"],
        how="inner",
    )
    merged = merged.rename(columns={factor_name: "computed_value"})
    if merged.empty:
        return {
            "factor_name": factor_name,
            "compared_count": 0,
            "exact_match_ratio": 0.0,
            "max_abs_error": float("nan"),
            "mean_abs_error": float("nan"),
            "cross_section_spearman_mean": float("nan"),
            "cross_section_pearson_mean": float("nan"),
            "mismatch_count": 0,
            "tolerance": tolerance,
            "mismatches": [],
        }

    merged["abs_error"] = (merged["computed_value"] - merged["truth_value"]).abs()
    both_nan = merged["computed_value"].isna() & merged["truth_value"].isna()
    exact_mask = both_nan | (merged["abs_error"] <= tolerance)

    spearman_values: list[float] = []
    pearson_values: list[float] = []
    valid_rows = merged[merged["computed_value"].notna() & merged["truth_value"].notna()]
    for _, date_slice in valid_rows.groupby("date"):
        if len(date_slice) < 3:
            continue
        spearman_values.append(_spearman_corr(date_slice["computed_value"], date_slice["truth_value"]))
        pearson_values.append(_corr(date_slice["computed_value"], date_slice["truth_value"]))

    mismatches = merged.loc[~exact_mask, ["date", "code", "computed_value", "truth_value", "abs_error"]].copy()
    mismatches["date"] = pd.to_datetime(mismatches["date"]).dt.strftime("%Y-%m-%d")

    return {
        "factor_name": factor_name,
        "compared_count": int(len(merged)),
        "exact_match_count": int(exact_mask.sum()),
        "exact_match_ratio": _to_float(exact_mask.mean()),
        "max_abs_error": _to_float(merged["abs_error"].max(skipna=True)),
        "mean_abs_error": _to_float(merged["abs_error"].mean(skipna=True)),
        "cross_section_spearman_mean": _to_float(np.nanmean(spearman_values)) if spearman_values else float("nan"),
        "cross_section_pearson_mean": _to_float(np.nanmean(pearson_values)) if pearson_values else float("nan"),
        "mismatch_count": int((~exact_mask).sum()),
        "tolerance": tolerance,
        "mismatches": mismatches.head(max_mismatches).to_dict(orient="records"),
    }


def export_truth_comparison(
    *,
    config: FactorLabWorkspaceConfig,
    spec: FactorResearchSpec,
    factor_frame: pd.DataFrame,
    truth_frame: pd.DataFrame,
    tolerance: float = 1e-12,
) -> tuple[str, dict[str, Any]]:
    config.ensure_directories()
    payload = compare_factor_to_truth(
        factor_frame,
        truth_frame,
        factor_name=spec.factor_name,
        tolerance=tolerance,
    )
    payload["generated_at"] = now_iso()
    payload["library"] = spec.library
    payload["source_document"] = spec.source_document
    path = config.truth_path(spec.library, spec.factor_name)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path), payload
