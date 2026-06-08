from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def compute_forward_returns(
    panel: pd.DataFrame,
    *,
    price_col: str = "close",
    code_col: str = "code",
    periods: int = 1,
) -> pd.Series:
    future_price = panel.groupby(code_col)[price_col].shift(-periods)
    return future_price / panel[price_col] - 1


def _mean_or_nan(values: list[float]) -> float:
    cleaned = [float(value) for value in values if pd.notna(value)]
    if not cleaned:
        return float("nan")
    return float(np.mean(cleaned))


def _std_or_nan(values: list[float]) -> float:
    cleaned = [float(value) for value in values if pd.notna(value)]
    if len(cleaned) < 2:
        return float("nan")
    return float(np.std(cleaned, ddof=1))


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


def summarize_factor_frame(
    factor_frame: pd.DataFrame,
    *,
    factor_names: list[str],
    forward_return_col: str = "forward_return_1d",
    date_col: str = "date",
) -> dict[str, Any]:
    metrics: dict[str, Any] = {}

    for factor_name in factor_names:
        series = factor_frame[factor_name]
        valid_mask = series.notna() & factor_frame[forward_return_col].notna()
        coverage = float(series.notna().mean())
        cross_section_rank_ic: list[float] = []
        cross_section_ic: list[float] = []
        long_short_spread: list[float] = []

        for _, date_slice in factor_frame.loc[valid_mask, [date_col, factor_name, forward_return_col]].groupby(date_col):
            if len(date_slice) < 3:
                continue

            factor_values = date_slice[factor_name]
            returns = date_slice[forward_return_col]
            cross_section_rank_ic.append(_spearman_corr(factor_values, returns))
            cross_section_ic.append(_corr(factor_values, returns))

            ranked = factor_values.rank(method="average", pct=True)
            top_mask = ranked >= 0.8
            bottom_mask = ranked <= 0.2
            if top_mask.any() and bottom_mask.any():
                spread = returns.loc[top_mask].mean() - returns.loc[bottom_mask].mean()
                long_short_spread.append(float(spread))

        rank_ic_mean = _mean_or_nan(cross_section_rank_ic)
        rank_ic_std = _std_or_nan(cross_section_rank_ic)
        metrics[factor_name] = {
            "coverage_ratio": coverage,
            "non_null_count": int(series.notna().sum()),
            "mean": float(series.mean(skipna=True)),
            "std": float(series.std(skipna=True)),
            "abs_mean": float(series.abs().mean(skipna=True)),
            "rank_ic_mean": rank_ic_mean,
            "rank_ic_std": rank_ic_std,
            "rank_ic_ir": float(rank_ic_mean / rank_ic_std) if pd.notna(rank_ic_mean) and pd.notna(rank_ic_std) and rank_ic_std != 0 else float("nan"),
            "pearson_ic_mean": _mean_or_nan(cross_section_ic),
            "long_short_mean": _mean_or_nan(long_short_spread),
            "cross_section_count": len(cross_section_rank_ic),
        }

    return {
        "factor_count": len(factor_names),
        "sample_count": int(len(factor_frame)),
        "forward_return_col": forward_return_col,
        "metrics": metrics,
    }


def build_alpha101_evaluation_report(
    panel: pd.DataFrame,
    factor_frame: pd.DataFrame,
    *,
    factor_names: list[str],
) -> dict[str, Any]:
    enriched = factor_frame.merge(panel[["date", "code", "close"]], on=["date", "code"], how="left")
    enriched["forward_return_1d"] = compute_forward_returns(
        panel[["date", "code", "close"]].sort_values(["code", "date"]).reset_index(drop=True),
        price_col="close",
    )
    summary = summarize_factor_frame(enriched, factor_names=factor_names)
    return {
        "library": "Alpha101",
        "dataset": {
            "rows": int(len(panel)),
            "codes": int(panel["code"].nunique()),
            "dates": int(panel["date"].nunique()),
        },
        "summary": summary,
    }


def build_factor_evaluation_report(
    panel: pd.DataFrame,
    factor_frame: pd.DataFrame,
    *,
    factor_names: list[str],
    library: str,
) -> dict[str, Any]:
    enriched = factor_frame.merge(panel[["date", "code", "close"]], on=["date", "code"], how="left")
    enriched["forward_return_1d"] = compute_forward_returns(
        panel[["date", "code", "close"]].sort_values(["code", "date"]).reset_index(drop=True),
        price_col="close",
    )
    summary = summarize_factor_frame(enriched, factor_names=factor_names)
    return {
        "library": library,
        "dataset": {
            "rows": int(len(panel)),
            "codes": int(panel["code"].nunique()),
            "dates": int(panel["date"].nunique()),
        },
        "summary": summary,
    }
