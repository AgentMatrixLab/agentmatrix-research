from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research_core.factor_lab.evaluation import summarize_factor_frame


def forward_daily_return_frame(panel: pd.DataFrame) -> pd.DataFrame:
    """Next-day close-to-close return per security (shift applied within each code)."""
    data = panel.sort_values(["code", "date"]).copy()
    data["date"] = pd.to_datetime(data["date"])
    grouped_close = data.groupby("code", sort=False)["close"]
    data["forward_return_1d"] = grouped_close.shift(-1) / data["close"] - 1
    return data[["date", "code", "forward_return_1d"]]


def _month_end_factor_values(factor_frame: pd.DataFrame, factor_names: list[str]) -> pd.DataFrame:
    data = factor_frame.copy()
    data["date"] = pd.to_datetime(data["date"])
    data["month"] = data["date"].dt.to_period("M")
    month_end_dates = data.groupby("month")["date"].transform("max")
    month_end = data[data["date"] == month_end_dates].copy()
    return month_end[["date", "code", *factor_names]]


def _forward_monthly_return(panel: pd.DataFrame) -> pd.DataFrame:
    data = panel.sort_values(["code", "date"]).copy()
    data["date"] = pd.to_datetime(data["date"])
    data["month"] = data["date"].dt.to_period("M")
    month_close = data.groupby(["code", "month"])["close"].last().reset_index()
    grouped_close = month_close.groupby("code", sort=False)["close"]
    month_close["forward_return_1m"] = grouped_close.shift(-1) / month_close["close"] - 1
    return month_close[["code", "month", "forward_return_1m"]]


def _build_merged_monthly_panel(
    market_panel: pd.DataFrame,
    factor_frame: pd.DataFrame,
    factor_names: list[str],
) -> pd.DataFrame:
    month_factors = _month_end_factor_values(factor_frame, factor_names)
    month_factors["month"] = month_factors["date"].dt.to_period("M")
    fwd = _forward_monthly_return(market_panel)
    merged = month_factors.merge(fwd, on=["code", "month"], how="inner")
    return merged.rename(columns={"forward_return_1m": "forward_return_1m"})


def compute_long_short_diagnostics(
    merged: pd.DataFrame,
    factor: str,
    *,
    n_quantiles: int = 10,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return monthly long-short spread series and average decile returns."""
    spread_records: list[dict[str, Any]] = []
    bucket_accum: dict[int, list[float]] = {i: [] for i in range(n_quantiles)}

    for date, slice_ in merged[[factor, "forward_return_1m", "date"]].dropna().groupby("date"):
        valid = slice_.copy()
        if len(valid) < n_quantiles * 5:
            continue
        try:
            valid["quantile"] = pd.qcut(
                valid[factor].rank(method="first"),
                q=n_quantiles,
                labels=False,
                duplicates="drop",
            )
        except ValueError:
            continue

        bucket_mean = valid.groupby("quantile", observed=True)["forward_return_1m"].mean()
        for quantile, mean_ret in bucket_mean.items():
            bucket_accum[int(quantile)].append(float(mean_ret))

        top = bucket_mean.get(n_quantiles - 1)
        bottom = bucket_mean.get(0)
        if top is not None and bottom is not None and pd.notna(top) and pd.notna(bottom):
            spread_records.append({"date": pd.Timestamp(date), "spread": float(top - bottom)})

    spread_df = pd.DataFrame(spread_records).sort_values("date")
    if not spread_df.empty:
        spread_df["nav"] = (1.0 + spread_df["spread"]).cumprod()

    bucket_rows = [
        {
            "quantile": quantile + 1,
            "mean_return": float(np.nanmean(values)),
            "n_periods": len(values),
        }
        for quantile, values in bucket_accum.items()
        if values
    ]
    bucket_df = pd.DataFrame(bucket_rows).sort_values("quantile")
    return spread_df, bucket_df


def run_effectiveness_suite(
    *,
    market_panel: pd.DataFrame,
    factor_frame: pd.DataFrame,
    factor_names: list[str],
    output_dir: str | Path,
) -> dict[str, Any]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    merged = _build_merged_monthly_panel(market_panel, factor_frame, factor_names)
    summary = summarize_factor_frame(
        merged.rename(columns={"forward_return_1m": "forward_return_1d"}),
        factor_names=factor_names,
        forward_return_col="forward_return_1d",
    )

    quantile_rows: list[dict[str, Any]] = []
    spread_series_map: dict[str, list[dict[str, Any]]] = {}
    bucket_map: dict[str, list[dict[str, Any]]] = {}

    for factor in factor_names:
        spread_df, bucket_df = compute_long_short_diagnostics(merged, factor)
        if not spread_df.empty:
            spread_export = spread_df.copy()
            spread_export["date"] = spread_export["date"].dt.strftime("%Y-%m-%d")
            spread_series_map[factor] = spread_export.to_dict(orient="records")
        else:
            spread_series_map[factor] = []
        bucket_map[factor] = bucket_df.to_dict(orient="records")

        mean_spread = float(spread_df["spread"].mean()) if not spread_df.empty else float("nan")
        quantile_rows.append(
            {
                "factor": factor,
                "long_short_spread_mean": mean_spread,
                "quantile_spread_count": int(len(spread_df)),
            }
        )

        spread_path = output_dir / f"{factor}_long_short_spread.csv"
        bucket_path = output_dir / f"{factor}_quantile_returns.csv"
        spread_df.to_csv(spread_path, index=False)
        bucket_df.to_csv(bucket_path, index=False)

    payload = {
        "factor_metrics": summary,
        "quantile_checks": quantile_rows,
        "spread_series": spread_series_map,
        "quantile_buckets": bucket_map,
    }
    out = output_dir / "effectiveness_report.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    payload["path"] = str(out.resolve())
    return payload