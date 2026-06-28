"""
Statistical Inference Engine — Bootstrap confidence intervals for factor evaluation.

Extends the existing evaluation module with:
1. Bootstrap IC confidence intervals (not just point estimates)
2. IC stability diagnostics (rolling IC decay, seasonality)
3. Multiple testing correction (Bonferroni, FDR)
4. Out-of-sample validation split

This gives interns, researchers, and AI agents the ability to say:
    "Factor alpha_X has Rank IC = 0.035 ± 0.008 (95% CI, N=252 dates)"
instead of just:
    "Factor alpha_X has Rank IC = 0.035"

Usage:
    from research_core.factor_lab.inference import (
        bootstrap_ic_confidence,
        ic_decay_analysis,
        multiple_testing_correction,
        out_of_sample_split,
    )

    # Bootstrap 95% CI for IC
    ci = bootstrap_ic_confidence(ic_series, n_bootstrap=10000, ci_level=0.95)

    # Check if IC decays over time
    decay = ic_decay_analysis(ic_series)

    # Apply FDR correction when testing many factors
    adjusted = multiple_testing_correction(pvalues_dict, method="fdr_bh")
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd
from scipy import stats

from research_core.factor_lab.runtime import FactorLabWorkspaceConfig, now_iso


# ═══════════════════════════════════════════════════════════════
# Bootstrap IC confidence intervals
# ═══════════════════════════════════════════════════════════════

def bootstrap_ic_confidence(
    ic_series: pd.Series | np.ndarray | list[float],
    *,
    n_bootstrap: int = 10000,
    ci_level: float = 0.95,
    seed: int = 42,
) -> dict[str, Any]:
    """Compute bootstrap confidence interval for IC mean.

    Uses percentile bootstrap (non-parametric, no distributional assumptions).
    This is the gold standard for IC significance testing — more robust than
    t-statistics when ICs are non-normal (fat-tailed, skewed).

    Args:
        ic_series: Array of IC values (one per date/cross-section)
        n_bootstrap: Number of bootstrap resamples (10k is standard)
        ci_level: Confidence level (default 0.95 for 95% CI)
        seed: Random seed for reproducibility

    Returns:
        Dict with:
        - ic_mean: point estimate
        - ic_std: standard deviation
        - ci_lower, ci_upper: confidence interval bounds
        - ic_ir: information ratio (mean/std)
        - ic_ir_ci: CI for IC_IR
        - p_value: two-sided bootstrap p-value (H0: IC=0)
        - ic_positive_ratio: fraction of positive IC days
        - ic_significant: True if CI does not include 0
        - n_samples: number of valid IC observations
        - n_bootstrap: number of bootstrap resamples
        - ci_level: confidence level used
    """
    values = pd.Series(ic_series).dropna().values
    n = len(values)

    if n < 3:
        return {
            "ic_mean": float("nan"),
            "ic_std": float("nan"),
            "ci_lower": float("nan"),
            "ci_upper": float("nan"),
            "ic_ir": float("nan"),
            "ic_ir_ci": [float("nan"), float("nan")],
            "p_value": float("nan"),
            "ic_positive_ratio": float("nan"),
            "ic_significant": False,
            "n_samples": n,
            "n_bootstrap": n_bootstrap,
            "ci_level": ci_level,
            "error": "Too few observations (n < 3)",
        }

    rng = np.random.default_rng(seed)

    # Bootstrap IC means
    boot_means = np.array([
        np.mean(rng.choice(values, size=n, replace=True))
        for _ in range(n_bootstrap)
    ])

    # Bootstrap IC_IR (mean/std ratio)
    boot_irs = np.zeros(n_bootstrap)
    for i in range(n_bootstrap):
        sample = rng.choice(values, size=n, replace=True)
        sample_std = np.std(sample, ddof=1)
        boot_irs[i] = np.mean(sample) / sample_std if sample_std > 0 else 0.0

    alpha = 1 - ci_level
    ci_lower = float(np.percentile(boot_means, 100 * alpha / 2))
    ci_upper = float(np.percentile(boot_means, 100 * (1 - alpha / 2)))
    ir_ci_lower = float(np.percentile(boot_irs, 100 * alpha / 2))
    ir_ci_upper = float(np.percentile(boot_irs, 100 * (1 - alpha / 2)))

    # Two-sided bootstrap p-value (H0: IC_mean = 0)
    # Shift bootstrap distribution to center at 0, count more extreme
    boot_centered = boot_means - np.mean(boot_means)
    observed = np.mean(values)
    p_value = float(np.mean(np.abs(boot_centered) >= np.abs(observed)))

    ic_mean = float(np.mean(values))
    ic_std = float(np.std(values, ddof=1))
    ic_ir = ic_mean / ic_std if ic_std > 0 else 0.0
    ic_positive = float(np.mean(values > 0))

    # Significant if CI does not include 0
    ic_significant = (ci_lower > 0) or (ci_upper < 0)

    return {
        "ic_mean": round(ic_mean, 6),
        "ic_std": round(ic_std, 6),
        "ci_lower": round(ci_lower, 6),
        "ci_upper": round(ci_upper, 6),
        "ci_width": round(ci_upper - ci_lower, 6),
        "ic_ir": round(ic_ir, 6),
        "ic_ir_ci": [round(ir_ci_lower, 6), round(ir_ci_upper, 6)],
        "p_value": round(p_value, 6),
        "ic_positive_ratio": round(ic_positive, 4),
        "ic_significant": ic_significant,
        "n_samples": n,
        "n_bootstrap": n_bootstrap,
        "ci_level": ci_level,
        "method": "percentile_bootstrap",
    }


def bootstrap_ic_confidence_multiple(
    ic_data: dict[str, pd.Series | np.ndarray | list[float]],
    *,
    n_bootstrap: int = 10000,
    ci_level: float = 0.95,
    seed: int = 42,
) -> dict[str, dict[str, Any]]:
    """Compute bootstrap CIs for multiple factors at once.

    Args:
        ic_data: {factor_name: IC_series}
        n_bootstrap: Bootstrap resamples per factor
        ci_level: Confidence level

    Returns:
        {factor_name: bootstrap_result_dict}
    """
    return {
        name: bootstrap_ic_confidence(
            series, n_bootstrap=n_bootstrap, ci_level=ci_level, seed=seed
        )
        for name, series in ic_data.items()
    }


# ═══════════════════════════════════════════════════════════════
# IC Decay / Stability Analysis
# ═══════════════════════════════════════════════════════════════

def ic_decay_analysis(
    ic_series: pd.Series | np.ndarray | list[float],
    *,
    window: int = 60,  # Rolling window size (trading days)
    step: int = 20,    # Step size for rolling windows
) -> dict[str, Any]:
    """Analyze IC stability over time — is the factor decaying?

    Computes rolling IC mean, detects trends, and tests for structural breaks.
    A healthy factor should have stable or improving IC over time.
    A decaying factor shows a significant downward trend.

    Args:
        ic_series: Array of IC values in chronological order
        window: Rolling window size (default 60 trading days ≈ 1 quarter)
        step: Step size for rolling windows

    Returns:
        Dict with:
        - rolling_means: list of {center_date_index, mean_ic, n_obs}
        - trend_slope: linear regression slope (negative = decaying)
        - trend_pvalue: p-value for trend significance
        - decay_warning: True if slope < 0 and p < 0.05
        - first_half_mean, second_half_mean: split-sample comparison
        - half_life_days: estimated days for IC to halve (if decaying)
    """
    values = pd.Series(ic_series).dropna()
    n = len(values)

    if n < window:
        return {
            "error": f"Need at least {window} observations for decay analysis (got {n})",
            "rolling_means": [],
            "trend_slope": 0.0,
            "trend_pvalue": 1.0,
            "decay_warning": False,
            "first_half_mean": float("nan"),
            "second_half_mean": float("nan"),
            "half_life_days": float("inf"),
        }

    # Rolling window means
    rolling = []
    for start in range(0, n - window + 1, step):
        end = start + window
        window_vals = values.iloc[start:end]
        rolling.append({
            "start_index": int(start),
            "end_index": int(end),
            "mean_ic": float(window_vals.mean()),
            "n_obs": len(window_vals),
        })

    # Linear trend test
    indices = np.arange(len(values)).reshape(-1, 1)
    slope, intercept, r_value, p_value, std_err = stats.linregress(
        indices.flatten(), values.values
    )

    decay_warning = (slope < 0) and (p_value < 0.05)

    # Split-sample comparison
    mid = n // 2
    first_half = float(values.iloc[:mid].mean())
    second_half = float(values.iloc[mid:].mean())

    # Half-life estimation: how many days until IC halves
    # Only meaningful if decaying
    if slope < 0 and abs(first_half) > 1e-10:
        half_life_days = abs(first_half / 2 / slope)
    else:
        half_life_days = float("inf")

    return {
        "rolling_means": rolling,
        "trend_slope": round(slope, 8),
        "trend_intercept": round(intercept, 6),
        "trend_r_squared": round(r_value ** 2, 6),
        "trend_pvalue": round(p_value, 6),
        "decay_warning": decay_warning,
        "first_half_mean": round(first_half, 6),
        "second_half_mean": round(second_half, 6),
        "split_difference": round(second_half - first_half, 6),
        "half_life_days": round(half_life_days, 1) if half_life_days != float("inf") else "inf",
        "n_total": n,
        "window": window,
    }


# ═══════════════════════════════════════════════════════════════
# Multiple testing correction
# ═══════════════════════════════════════════════════════════════

def multiple_testing_correction(
    pvalues: dict[str, float],
    *,
    method: str = "fdr_bh",  # Benjamini-Hochberg FDR
    alpha: float = 0.05,
) -> dict[str, Any]:
    """Apply multiple testing correction to factor p-values.

    When testing 101 factors, ~5 will appear significant by chance (α=0.05).
    FDR correction controls the expected proportion of false positives.

    Args:
        pvalues: {factor_name: p_value} from bootstrap or t-test
        method: "fdr_bh" (Benjamini-Hochberg), "bonferroni", or "none"
        alpha: Significance threshold

    Returns:
        Dict with:
        - adjusted: {factor_name: adjusted_pvalue}
        - significant: {factor_name: bool}
        - n_significant: number of factors significant after correction
        - method: correction method used
    """
    names = list(pvalues.keys())
    raw = np.array([pvalues[n] for n in names])

    if method == "bonferroni":
        adjusted_values = np.minimum(raw * len(names), 1.0)
    elif method == "fdr_bh":
        # Benjamini-Hochberg procedure
        n = len(raw)
        sorted_idx = np.argsort(raw)
        sorted_p = raw[sorted_idx]
        adjusted = np.ones(n)
        for i in range(n - 1, -1, -1):
            adjusted[i] = min(sorted_p[i] * n / (i + 1), 1.0)
            if i < n - 1:
                adjusted[i] = min(adjusted[i], adjusted[i + 1])
        adjusted_values = np.ones(n)
        adjusted_values[sorted_idx] = adjusted
    else:
        adjusted_values = raw.copy()

    adjusted = {
        name: round(float(adj), 6)
        for name, adj in zip(names, adjusted_values)
    }
    significant = {
        name: float(adj) < alpha
        for name, adj in zip(names, adjusted_values)
    }

    return {
        "method": method,
        "n_total": len(names),
        "n_significant": sum(significant.values()),
        "alpha": alpha,
        "adjusted_pvalues": adjusted,
        "significant": significant,
    }


# ═══════════════════════════════════════════════════════════════
# Out-of-sample split
# ═══════════════════════════════════════════════════════════════

def out_of_sample_split(
    panel: pd.DataFrame,
    *,
    train_ratio: float = 0.7,
    date_col: str = "date",
) -> dict[str, Any]:
    """Split panel into training and out-of-sample periods.

    Used to detect overfitting: a factor that works in-sample but fails
    out-of-sample is likely overfit.

    Args:
        panel: DataFrame with [date, code, ...]
        train_ratio: Fraction of dates for training
        date_col: Date column name

    Returns:
        Dict with:
        - train_start, train_end: training period
        - test_start, test_end: out-of-sample period
        - train_dates, test_dates: number of unique dates in each split
        - train_panel, test_panel: the split DataFrames
    """
    dates = sorted(panel[date_col].unique())
    n = len(dates)
    split_idx = int(n * train_ratio)
    split_date = dates[split_idx]

    train_panel = panel[panel[date_col] < split_date]
    test_panel = panel[panel[date_col] >= split_date]

    return {
        "train_start": str(dates[0]),
        "train_end": str(dates[split_idx - 1]),
        "test_start": str(split_date),
        "test_end": str(dates[-1]),
        "n_train_dates": split_idx,
        "n_test_dates": n - split_idx,
        "train_panel": train_panel,
        "test_panel": test_panel,
    }


def out_of_sample_ic_compare(
    factor_frame: pd.DataFrame,
    forward_returns: pd.Series,
    factor_name: str,
    *,
    train_ratio: float = 0.7,
    date_col: str = "date",
    code_col: str = "code",
) -> dict[str, Any]:
    """Compare factor IC in-sample vs out-of-sample.

    A large drop in IC from train→test indicates overfitting.

    Returns:
        Dict with in-sample and out-of-sample IC statistics.
    """
    full = factor_frame[[date_col, code_col, factor_name]].copy()
    full["fwd_ret"] = forward_returns

    # Split
    dates = sorted(full[date_col].unique())
    split_idx = int(len(dates) * train_ratio)
    split_date = dates[split_idx]

    def compute_ics(df):
        """Compute cross-sectional Spearman ICs for a date slice."""
        ics = []
        for _, group in df.groupby(date_col):
            valid = group.dropna(subset=[factor_name, "fwd_ret"])
            if len(valid) < 20:
                continue
            ic = valid[factor_name].rank().corr(valid["fwd_ret"].rank())
            if pd.notna(ic):
                ics.append(ic)
        return ics

    is_ics = compute_ics(full[full[date_col] < split_date])
    oos_ics = compute_ics(full[full[date_col] >= split_date])

    is_result = bootstrap_ic_confidence(is_ics) if is_ics else None
    oos_result = bootstrap_ic_confidence(oos_ics) if oos_ics else None

    decay_ratio = None
    if is_result and oos_result:
        is_mean = is_result["ic_mean"]
        oos_mean = oos_result["ic_mean"]
        if abs(is_mean) > 1e-10:
            decay_ratio = oos_mean / is_mean

    overfit_warning = (
        decay_ratio is not None and
        decay_ratio < 0.5 and
        (is_result and is_result["ic_significant"])
    )

    return {
        "factor_name": factor_name,
        "split_date": str(split_date),
        "in_sample": is_result,
        "out_of_sample": oos_result,
        "decay_ratio": round(decay_ratio, 4) if decay_ratio is not None else None,
        "overfit_warning": overfit_warning,
        "n_train_dates": len(is_ics),
        "n_test_dates": len(oos_ics),
    }


# ═══════════════════════════════════════════════════════════════
# Export helper
# ═══════════════════════════════════════════════════════════════

def export_inference_report(
    inference_results: dict[str, Any],
    config: FactorLabWorkspaceConfig | None = None,
    filename: str = "inference_report",
) -> str:
    """Export inference results to runtime store.

    Returns:
        Path string.
    """
    if config is None:
        config = FactorLabWorkspaceConfig()
    config.ensure_directories()

    report_dir = config.runtime_root / "inference"
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"{filename}.json"

    # Convert any DataFrames to dicts for JSON serialization
    clean = {}
    for k, v in inference_results.items():
        if isinstance(v, pd.DataFrame):
            clean[k] = v.to_dict(orient="records")
        elif isinstance(v, (np.integer,)):
            clean[k] = int(v)
        elif isinstance(v, (np.floating,)):
            clean[k] = float(v)
        elif isinstance(v, np.ndarray):
            clean[k] = v.tolist()
        else:
            clean[k] = v

    clean["generated_at"] = now_iso()
    path.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)
