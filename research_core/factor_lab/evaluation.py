"""
Factor IC Evaluation Pipeline — production-grade factor quality assessment.

Evaluates alpha factors across five dimensions:
  1. IC Analysis (Rank IC, Pearson IC, ICIR)
  2. IC Decay (how long does the signal last?)
  3. Turnover Analysis (how much does the portfolio change?)
  4. Sector/Industry Neutrality (is it just a sector bet?)
  5. Factor Correlation & Redundancy Detection

All methods work with the standard long-panel format (date, code, factor_value, [next_return]).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Any

from research_core.factor_lab.operators import cross_sectional_rank, safe_div


# ─── Data Structures ────────────────────────────────────────────

@dataclass(slots=True)
class ICResult:
    """Single-period IC statistics."""
    rank_ic: float
    pearson_ic: float
    ic_positive_ratio: float = 0.0
    n_stocks: int = 0
    n_dates: int = 0


@dataclass(slots=True)
class ICIREvaluation:
    """Multi-period IC analysis with decay and IR."""
    mean_rank_ic: float
    rank_icir: float
    mean_pearson_ic: float
    pearson_icir: float
    ic_std: float
    ic_positive_ratio: float
    ic_series: pd.Series = field(default_factory=pd.Series)
    decay_series: pd.Series = field(default_factory=pd.Series)
    n_dates: int = 0


@dataclass(slots=True)
class TurnoverResult:
    """Factor turnover statistics."""
    mean_turnover: float
    median_turnover: float
    turnover_series: pd.Series = field(default_factory=pd.Series)
    auto_corr: float = 0.0


@dataclass(slots=True)
class SectorNeutralityResult:
    """Sector neutrality test results."""
    raw_ic: float
    neutral_ic: float
    ic_retained_ratio: float  # neutral_ic / raw_ic — higher = more alpha left after stripping sectors
    sector_r_squared: float  # how much of factor variance is explained by sectors


@dataclass(slots=True)
class FactorEvaluationReport:
    """Complete factor evaluation report."""
    factor_name: str
    ic_eval: ICIREvaluation | None = None
    turnover: TurnoverResult | None = None
    sector_neutrality: SectorNeutralityResult | None = None
    correlation_with: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    status: str = "pending"  # pass / warn / fail


# ─── IC Analysis ────────────────────────────────────────────────

def compute_ic(
    df: pd.DataFrame,
    factor_col: str = "factor_value",
    return_col: str = "next_return",
    *,
    date_col: str = "date",
    method: str = "rank",
) -> pd.Series:
    """Compute cross-sectional IC for each date.

    Args:
        df: Long-panel with [date_col, factor_col, return_col].
        method: 'rank' (Spearman) or 'pearson'.

    Returns:
        Series of daily IC values indexed by date.
    """
    if method == "rank":
        ranked = df.copy()
        ranked["_factor_rank"] = cross_sectional_rank(ranked, factor_col, date_col=date_col)
        ranked["_return_rank"] = cross_sectional_rank(ranked, return_col, date_col=date_col)
        ic = ranked.groupby(date_col).apply(
            lambda g: g["_factor_rank"].corr(g["_return_rank"])
        )
    else:
        ic = df.groupby(date_col).apply(
            lambda g: g[factor_col].corr(g[return_col])
        )
    return ic.dropna()


def evaluate_ic(
    df: pd.DataFrame,
    factor_col: str = "factor_value",
    return_col: str = "next_return",
    *,
    date_col: str = "date",
    decay_horizons: list[int] | None = None,
) -> ICIREvaluation:
    """Full IC evaluation including decay analysis.

    Args:
        df: Long-panel sorted by (date, code).
        decay_horizons: List of lag periods to check IC persistence.
                        Default: [1, 3, 5, 10, 20].
    """
    if decay_horizons is None:
        decay_horizons = [1, 3, 5, 10, 20]

    rank_ic = compute_ic(df, factor_col, return_col, date_col=date_col, method="rank")
    pearson_ic = compute_ic(df, factor_col, return_col, date_col=date_col, method="pearson")

    mean_rank = float(rank_ic.mean())
    ic_std = float(rank_ic.std())
    rank_icir = mean_rank / ic_std if ic_std > 0 else 0.0
    pos_ratio = float((rank_ic > 0).mean())

    # IC Decay — shift factor forward and recompute IC
    decay_values = {}
    decay_values[0] = mean_rank
    for horizon in decay_horizons:
        df_shifted = df.copy()
        df_shifted[return_col] = df_shifted.groupby("code")[return_col].shift(-horizon)
        decay_ic = compute_ic(df_shifted, factor_col, return_col, date_col=date_col, method="rank")
        decay_values[horizon] = float(decay_ic.mean())

    decay_series = pd.Series(decay_values).sort_index()

    return ICIREvaluation(
        mean_rank_ic=mean_rank,
        rank_icir=rank_icir,
        mean_pearson_ic=float(pearson_ic.mean()),
        pearson_icir=float(pearson_ic.mean()) / float(pearson_ic.std()) if float(pearson_ic.std()) > 0 else 0.0,
        ic_std=ic_std,
        ic_positive_ratio=pos_ratio,
        ic_series=rank_ic,
        decay_series=decay_series,
        n_dates=len(rank_ic),
    )


# ─── Turnover Analysis ───────────────────────────────────────────

def compute_turnover(
    df: pd.DataFrame,
    factor_col: str = "factor_value",
    *,
    date_col: str = "date",
    code_col: str = "code",
    top_quantile: float = 0.2,
) -> TurnoverResult:
    """Compute factor turnover — how much does the top/bottom basket change day-to-day?

    Args:
        top_quantile: Fraction to use for top/bottom basket (e.g. 0.2 = top 20%).
    """
    df_sorted = df.sort_values([date_col, code_col]).copy()
    df_sorted["_rank"] = df_sorted.groupby(date_col)[factor_col].rank(pct=True)

    dates = sorted(df_sorted[date_col].unique())
    turnover_rates = []
    prev_top = None

    for d in dates:
        today = df_sorted[df_sorted[date_col] == d]
        top_codes = set(today[today["_rank"] >= (1 - top_quantile)][code_col])

        if prev_top is not None:
            if prev_top:
                stayed = len(top_codes & prev_top)
                turnover = 1.0 - stayed / len(prev_top)
            else:
                turnover = 1.0
            turnover_rates.append((d, turnover))
        prev_top = top_codes

    to_series = pd.Series(
        [t for _, t in turnover_rates],
        index=[d for d, _ in turnover_rates],
    )

    # Auto-correlation of factor values (proxy for signal stability)
    df_sorted["_prev_factor"] = df_sorted.groupby(code_col)[factor_col].shift(1)
    valid = df_sorted.dropna(subset=["_prev_factor"])
    auto_corr = float(valid[factor_col].corr(valid["_prev_factor"])) if len(valid) > 1 else 0.0

    return TurnoverResult(
        mean_turnover=float(to_series.mean()) if len(to_series) > 0 else 0.0,
        median_turnover=float(to_series.median()) if len(to_series) > 0 else 0.0,
        turnover_series=to_series,
        auto_corr=auto_corr,
    )


# ─── Sector Neutrality ───────────────────────────────────────────

def test_sector_neutrality(
    df: pd.DataFrame,
    factor_col: str = "factor_value",
    return_col: str = "next_return",
    sector_col: str = "sector",
    *,
    date_col: str = "date",
) -> SectorNeutralityResult:
    """Test if factor alpha survives sector neutralization.

    A factor that's just a sector bet will see its IC collapse after neutralization.
    A genuine alpha should retain most of its IC.

    Args:
        sector_col: Column with sector/industry labels.
    """
    if sector_col not in df.columns:
        return SectorNeutralityResult(
            raw_ic=0.0, neutral_ic=0.0,
            ic_retained_ratio=0.0, sector_r_squared=0.0,
        )

    raw_ic = compute_ic(df, factor_col, return_col, date_col=date_col, method="rank")

    # Sector-neutralize factor values
    df_neutral = df.copy()
    df_neutral[factor_col] = df_neutral[factor_col] - df_neutral.groupby(
        [date_col, sector_col]
    )[factor_col].transform("mean")

    neutral_ic = compute_ic(df_neutral, factor_col, return_col, date_col=date_col, method="rank")

    mean_raw = float(raw_ic.mean())
    mean_neutral = float(neutral_ic.mean())

    # How much of factor cross-sectional variance is explained by sectors?
    r_squares = []
    for date, group in df.groupby(date_col):
        if sector_col in group.columns and group[sector_col].nunique() > 1:
            try:
                import statsmodels.api as sm
                dummies = pd.get_dummies(group[sector_col], drop_first=True).astype(float)
                if dummies.shape[1] > 0 and len(dummies) > dummies.shape[1] + 1:
                    model = sm.OLS(group[factor_col].fillna(0), sm.add_constant(dummies)).fit()
                    r_squares.append(model.rsquared)
            except Exception:
                pass
    sector_r2 = float(np.mean(r_squares)) if r_squares else 0.0

    return SectorNeutralityResult(
        raw_ic=mean_raw,
        neutral_ic=mean_neutral,
        ic_retained_ratio=safe_div(
            pd.Series([mean_neutral]), pd.Series([mean_raw])
        ).iloc[0] if abs(mean_raw) > 1e-10 else 0.0,
        sector_r_squared=sector_r2,
    )


# ─── Factor Correlation & Redundancy ─────────────────────────────

def compute_factor_correlation(
    factor_dfs: dict[str, pd.DataFrame],
    *,
    date_col: str = "date",
    code_col: str = "code",
    factor_col: str = "factor_value",
) -> pd.DataFrame:
    """Cross-sectional correlation matrix across multiple factors.

    Args:
        factor_dfs: {factor_name: df} mapping. Each df must have [date, code, factor_value].

    Returns:
        DataFrame: correlation matrix (factor_name × factor_name).
    """
    names = list(factor_dfs.keys())
    merged = factor_dfs[names[0]][[date_col, code_col]].copy()

    for name in names:
        fdf = factor_dfs[name][[date_col, code_col, factor_col]].copy()
        fdf = fdf.rename(columns={factor_col: name})
        merged = merged.merge(fdf, on=[date_col, code_col], how="inner")

    corr_matrix = merged[names].corr()
    return corr_matrix


def flag_redundant_factors(
    corr_matrix: pd.DataFrame,
    threshold: float = 0.85,
) -> list[tuple[str, str, float]]:
    """Flag highly correlated factor pairs.

    Returns:
        List of (factor_a, factor_b, correlation) for pairs above threshold.
    """
    redundant = []
    names = list(corr_matrix.columns)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            corr = abs(corr_matrix.iloc[i, j])
            if corr >= threshold:
                redundant.append((names[i], names[j], float(corr)))
    return sorted(redundant, key=lambda x: -x[2])


# ─── Full Evaluation ────────────────────────────────────────────

def evaluate_factor(
    df: pd.DataFrame,
    factor_name: str,
    factor_col: str = "factor_value",
    return_col: str = "next_return",
    *,
    date_col: str = "date",
    code_col: str = "code",
    sector_col: str = "sector",
    decay_horizons: list[int] | None = None,
    ic_threshold: float = 0.02,
    turnover_warn: float = 0.7,
) -> FactorEvaluationReport:
    """Run the full factor evaluation suite.

    Args:
        df: Long-panel with [date, code, factor_value, next_return, (sector)].
        ic_threshold: Minimum |mean Rank IC| to pass.
        turnover_warn: Turnover rate above which to warn.

    Returns:
        FactorEvaluationReport with all results and pass/warn/fail status.
    """
    report = FactorEvaluationReport(factor_name=factor_name)
    warnings = []

    # 1. IC analysis
    try:
        report.ic_eval = evaluate_ic(df, factor_col, return_col, date_col=date_col, decay_horizons=decay_horizons)
        if abs(report.ic_eval.mean_rank_ic) < ic_threshold:
            warnings.append(f"Rank IC |{report.ic_eval.mean_rank_ic:.4f}| < {ic_threshold} — may be too weak")
        if report.ic_eval.rank_icir < 0.3:
            warnings.append(f"ICIR {report.ic_eval.rank_icir:.2f} < 0.3 — signal too noisy")
    except Exception as e:
        warnings.append(f"IC evaluation failed: {e}")

    # 2. Turnover
    try:
        report.turnover = compute_turnover(df, factor_col, date_col=date_col, code_col=code_col)
        if report.turnover.mean_turnover > turnover_warn:
            warnings.append(f"Mean turnover {report.turnover.mean_turnover:.2%} > {turnover_warn:.0%} — may be too costly")
    except Exception as e:
        warnings.append(f"Turnover evaluation failed: {e}")

    # 3. Sector neutrality
    if sector_col in df.columns:
        try:
            report.sector_neutrality = test_sector_neutrality(
                df, factor_col, return_col, sector_col, date_col=date_col
            )
            if report.sector_neutrality.ic_retained_ratio < 0.3:
                warnings.append(
                    f"Sector neutrality: only {report.sector_neutrality.ic_retained_ratio:.0%} "
                    f"of IC retained — factor may be mostly a sector bet"
                )
        except Exception as e:
            warnings.append(f"Sector neutrality test failed: {e}")

    # Determine status
    fail_count = sum(1 for w in warnings if "failed" in w.lower() or "too weak" in w.lower())
    if fail_count > 1:
        report.status = "fail"
    elif warnings:
        report.status = "warn"
    else:
        report.status = "pass"

    report.warnings = warnings
    return report


def evaluation_summary(report: FactorEvaluationReport) -> str:
    """One-line summary string for a factor evaluation."""
    ic = report.ic_eval
    parts = [f"[{report.status.upper()}] {report.factor_name}"]

    if ic:
        parts.append(f"IC={ic.mean_rank_ic:.4f}")
        parts.append(f"ICIR={ic.rank_icir:.2f}")
        parts.append(f"+ve%={ic.ic_positive_ratio:.0%}")

    if report.turnover:
        parts.append(f"TO={report.turnover.mean_turnover:.0%}")

    if report.sector_neutrality:
        parts.append(f"SecR²={report.sector_neutrality.sector_r_squared:.0%}")

    if report.warnings:
        parts.append(f"⚠️×{len(report.warnings)}")

    return " | ".join(parts)


def compute_forward_returns(df, periods=1, price_col="close", date_col="date", code_col="code"):
    """Compute forward returns for factor evaluation."""
    df_sorted = df.sort_values([code_col, date_col]).copy()
    df_sorted["_fwd_price"] = df_sorted.groupby(code_col)[price_col].shift(-periods)
    df_sorted["next_return"] = (df_sorted["_fwd_price"] - df_sorted[price_col]) / df_sorted[price_col].replace(0, np.nan)
    return df_sorted["next_return"]


# Backward-compatible shims for existing service.py imports


def build_factor_evaluation_report(
    panel: pd.DataFrame,
    factor_frame: pd.DataFrame,
    *,
    factor_names: list[str],
    library: str,
) -> dict[str, Any]:
    """Legacy wrapper — compatible with service.py callers. Returns per-factor IC summary."""
    metrics: dict[str, dict[str, float]] = {}
    for fname in factor_names:
        if fname not in factor_frame.columns:
            continue
        merged = panel[["date", "code", "close"]].merge(
            factor_frame[["date", "code", fname]], on=["date", "code"], how="left"
        )
        merged["forward_return_1d"] = compute_forward_returns(
            panel[["date", "code", "close"]].sort_values(["code", "date"]).reset_index(drop=True),
            price_col="close",
        )
        ic_series = merged.groupby("date").apply(
            lambda g: g[[fname, "forward_return_1d"]].dropna().corr(method="spearman").iloc[0, 1]
            if len(g.dropna(subset=[fname, "forward_return_1d"])) >= 3
            else None
        ).dropna()
        n_total = int(panel["code"].nunique() * panel["date"].nunique())
        n_obs = int(merged[fname].notna().sum())
        metrics[fname] = {
            "coverage_ratio": round(n_obs / max(n_total, 1), 4),
            "rank_ic_mean": round(float(ic_series.mean()), 6) if len(ic_series) > 0 else 0.0,
            "rank_ic_ir": round(float(ic_series.mean() / max(ic_series.std(), 1e-9)), 6) if len(ic_series) > 0 else 0.0,
            "long_short_mean": round(float(ic_series.mean()), 6) if len(ic_series) > 0 else 0.0,
            # Required by validation.py:build_validation_report
            "non_null_count": n_obs,
            "cross_section_count": int(panel["date"].nunique()),
        }
    return {
        "library": library,
        "dataset": {
            "rows": int(len(panel)),
            "codes": int(panel["code"].nunique()),
            "dates": int(panel["date"].nunique()),
        },
        "summary": {"metrics": metrics, "factor_count": len(metrics)},
    }


def build_alpha101_evaluation_report(df, factor_frame, *, factor_names=None, **kwargs):
    """Legacy wrapper for alpha101 evaluation. Delegates to build_factor_evaluation_report."""
    if factor_names is None:
        factor_names = kwargs.pop("factor_names", [])
    return build_factor_evaluation_report(
        df, factor_frame, factor_names=list(factor_names), library=kwargs.get("library", "Alpha101")
    )


# backward-compat alias — ci_factor_validate.py still imports this name
summarize_factor_frame = build_factor_evaluation_report


__all__ = [
    "ICResult", "ICIREvaluation", "TurnoverResult",
    "SectorNeutralityResult", "FactorEvaluationReport",
    "compute_ic", "evaluate_ic", "compute_turnover",
    "test_sector_neutrality", "compute_factor_correlation",
    "flag_redundant_factors", "evaluate_factor", "evaluation_summary",
    "build_factor_evaluation_report", "build_alpha101_evaluation_report",
    "compute_forward_returns", "summarize_factor_frame",
]
