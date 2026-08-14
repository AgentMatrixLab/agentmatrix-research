from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research_core.factor_lab.runtime import now_iso


def attach_forward_returns(
    panel: pd.DataFrame,
    factor_frame: pd.DataFrame,
    *,
    horizon: int = 1,
    price_col: str = "close",
) -> pd.DataFrame:
    prices = panel[["date", "code", price_col]].copy()
    prices["date"] = pd.to_datetime(prices["date"])
    prices = prices.sort_values(["code", "date"]).reset_index(drop=True)
    prices["forward_return"] = prices.groupby("code", sort=False)[price_col].shift(-horizon) / prices[price_col] - 1
    enriched = factor_frame.copy()
    enriched["date"] = pd.to_datetime(enriched["date"])
    return enriched.merge(prices[["date", "code", "forward_return"]], on=["date", "code"], how="left")


def _corr(left: pd.Series, right: pd.Series) -> float:
    aligned = pd.concat([left, right], axis=1).dropna()
    if len(aligned) < 3:
        return float("nan")
    return float(aligned.iloc[:, 0].astype(float).corr(aligned.iloc[:, 1].astype(float)))


def _spearman(left: pd.Series, right: pd.Series) -> float:
    aligned = pd.concat([left, right], axis=1).dropna()
    if len(aligned) < 3:
        return float("nan")
    return _corr(aligned.iloc[:, 0].rank(method="average"), aligned.iloc[:, 1].rank(method="average"))


def _mean(values: list[float]) -> float:
    cleaned = [float(item) for item in values if pd.notna(item)]
    return float(np.mean(cleaned)) if cleaned else float("nan")


def _std(values: list[float]) -> float:
    cleaned = [float(item) for item in values if pd.notna(item)]
    return float(np.std(cleaned, ddof=1)) if len(cleaned) > 1 else float("nan")


def _max_drawdown(returns: pd.Series) -> float:
    clean = returns.dropna().astype(float)
    if clean.empty:
        return float("nan")
    nav = (1.0 + clean).cumprod()
    return float((nav / nav.cummax() - 1.0).min())


def _sharpe(returns: pd.Series, annualization: float) -> float:
    clean = returns.dropna().astype(float)
    if len(clean) < 2:
        return float("nan")
    vol = float(clean.std(ddof=1))
    if vol == 0.0:
        return float("nan")
    return float(clean.mean() / vol * math.sqrt(annualization))


def _two_sided_null_probability(t_stat: float) -> float:
    if pd.isna(t_stat):
        return 1.0
    return float(math.erfc(abs(float(t_stat)) / math.sqrt(2.0)))


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    return value


def _quantile_summary(
    daily: pd.DataFrame,
    *,
    factor_name: str,
    quantiles: int,
) -> tuple[pd.DataFrame, pd.Series]:
    rows: list[dict[str, Any]] = []
    long_short: dict[pd.Timestamp, float] = {}
    for date_value, date_slice in daily[[factor_name, "forward_return", "date"]].dropna().groupby("date"):
        if len(date_slice) < quantiles:
            continue
        ranks = date_slice[factor_name].rank(method="first")
        bucket = pd.qcut(ranks, quantiles, labels=False, duplicates="drop")
        tmp = date_slice.assign(quantile=bucket.astype(float) + 1)
        grouped = tmp.groupby("quantile")["forward_return"].mean()
        for quantile, value in grouped.items():
            rows.append({"date": date_value, "quantile": int(quantile), "return": float(value)})
        if 1 in grouped.index and float(quantiles) in grouped.index:
            long_short[pd.Timestamp(date_value)] = float(grouped.loc[float(quantiles)] - grouped.loc[1])
    table = pd.DataFrame(rows)
    return table, pd.Series(long_short, name=f"{factor_name}_long_short").sort_index()


def _turnover(daily: pd.DataFrame, *, factor_name: str) -> float:
    autocorrs: list[float] = []
    previous: pd.Series | None = None
    for _, date_slice in daily[["date", "code", factor_name]].dropna().sort_values(["date", "code"]).groupby("date"):
        ranks = date_slice.set_index("code")[factor_name].rank(pct=True)
        if previous is not None:
            aligned = pd.concat([previous, ranks], axis=1).dropna()
            if len(aligned) >= 3:
                autocorrs.append(float(aligned.iloc[:, 0].corr(aligned.iloc[:, 1])))
        previous = ranks
    mean_autocorr = _mean(autocorrs)
    return float(1.0 - mean_autocorr) if pd.notna(mean_autocorr) else float("nan")


def _ic_by_date(daily: pd.DataFrame, *, factor_name: str) -> pd.Series:
    values: dict[pd.Timestamp, float] = {}
    for date_value, date_slice in daily[["date", factor_name, "forward_return"]].dropna().groupby("date"):
        values[pd.Timestamp(date_value)] = _spearman(date_slice[factor_name], date_slice["forward_return"])
    return pd.Series(values, name=factor_name).sort_index()


def _ic_decay(panel: pd.DataFrame, factor_frame: pd.DataFrame, *, factor_name: str, horizons: tuple[int, ...]) -> dict[str, float]:
    decay: dict[str, float] = {}
    for horizon in horizons:
        daily = attach_forward_returns(panel, factor_frame[["date", "code", factor_name]], horizon=horizon)
        decay[f"{horizon}d"] = float(_ic_by_date(daily, factor_name=factor_name).mean(skipna=True))
    return decay


def _red_flags(metrics: dict[str, Any]) -> list[dict[str, Any]]:
    checks = [
        ("coverage_ratio", metrics.get("coverage_ratio", 0.0) < 0.30, "reject", "Coverage below 30%."),
        ("ic_days", metrics.get("ic_days", 0) < 120, "warn", "Fewer than 120 valid IC days."),
        ("rank_ic_mean", abs(metrics.get("rank_ic_mean", 0.0) or 0.0) < 0.01, "warn", "Absolute Rank IC below 1%."),
        ("rank_ic_t_stat", abs(metrics.get("rank_ic_t_stat", 0.0) or 0.0) < 1.65, "warn", "Rank IC t-stat below 1.65."),
        ("null_probability", metrics.get("null_probability", 1.0) > 0.80, "warn", "High null probability."),
        ("turnover", metrics.get("turnover_daily", 0.0) > 0.60, "warn", "Estimated daily turnover above 60%."),
        (
            "monotonicity",
            abs(metrics.get("monotonicity_spearman", 0.0) or 0.0) < 0.50,
            "warn",
            "Quantile return monotonicity is weak.",
        ),
        ("drawdown", metrics.get("long_short_max_drawdown", 0.0) < -0.30, "warn", "Long-short drawdown worse than -30%."),
    ]
    return [
        {"metric": metric, "severity": severity, "message": message}
        for metric, failed, severity, message in checks
        if bool(failed)
    ]


def summarize_internal_validation(
    panel: pd.DataFrame,
    factor_frame: pd.DataFrame,
    *,
    factor_names: list[str],
    horizon: int = 1,
    quantiles: int = 5,
    decay_horizons: tuple[int, ...] = (1, 5, 10, 20),
) -> dict[str, Any]:
    daily = attach_forward_returns(panel, factor_frame, horizon=horizon)
    results: dict[str, Any] = {}
    for factor_name in factor_names:
        valid = daily[factor_name].notna() & daily["forward_return"].notna()
        ic = _ic_by_date(daily.loc[valid], factor_name=factor_name)
        ic_mean = float(ic.mean(skipna=True)) if not ic.empty else float("nan")
        ic_std = float(ic.std(ddof=1, skipna=True)) if len(ic.dropna()) > 1 else float("nan")
        ic_days = int(ic.notna().sum())
        t_stat = float(ic_mean / (ic_std / math.sqrt(ic_days))) if ic_days > 1 and pd.notna(ic_std) and ic_std != 0 else float("nan")
        quantile_table, long_short = _quantile_summary(daily.loc[valid], factor_name=factor_name, quantiles=quantiles)
        quantile_means = quantile_table.groupby("quantile")["return"].mean() if not quantile_table.empty else pd.Series(dtype=float)
        monotonicity = _spearman(pd.Series(quantile_means.index, dtype=float), quantile_means) if len(quantile_means) >= 3 else float("nan")
        yearly = (
            ic.groupby(ic.index.year).agg(["mean", "std", "count"]).rename(columns={"count": "ic_days"}).to_dict(orient="index")
            if not ic.empty
            else {}
        )
        metrics = {
            "coverage_ratio": float(daily[factor_name].notna().mean()),
            "non_null_count": int(daily[factor_name].notna().sum()),
            "rank_ic_mean": ic_mean,
            "rank_ic_std": ic_std,
            "rank_ic_t_stat": t_stat,
            "rank_ic_ir": float(ic_mean / ic_std) if pd.notna(ic_mean) and pd.notna(ic_std) and ic_std != 0 else float("nan"),
            "ic_days": ic_days,
            "ic_positive_ratio": float((ic > 0).mean()) if ic_days else float("nan"),
            "null_probability": _two_sided_null_probability(t_stat),
            "long_short_mean": float(long_short.mean(skipna=True)) if not long_short.empty else float("nan"),
            "long_short_sharpe": _sharpe(long_short, 252.0 / max(1, horizon)),
            "long_short_max_drawdown": _max_drawdown(long_short),
            "turnover_daily": _turnover(daily, factor_name=factor_name),
            "monotonicity_spearman": monotonicity,
            "ic_decay": _ic_decay(panel, factor_frame, factor_name=factor_name, horizons=decay_horizons),
            "yearly_ic": {str(year): values for year, values in yearly.items()},
        }
        results[factor_name] = {
            "metrics": metrics,
            "red_flags": _red_flags(metrics),
            "quantile_returns": quantile_means.to_dict(),
        }
    return {
        "generated_at": now_iso(),
        "horizon": horizon,
        "quantiles": quantiles,
        "factor_count": len(factor_names),
        "sample": {
            "rows": int(len(panel)),
            "codes": int(panel["code"].nunique()),
            "dates": int(panel["date"].nunique()),
        },
        "factors": results,
    }


def write_internal_validation_report(report: dict[str, Any], path: str | Path) -> str:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(_json_safe(report), ensure_ascii=False, indent=2), encoding="utf-8")
    return str(output_path)
