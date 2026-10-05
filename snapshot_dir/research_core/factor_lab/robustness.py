"""Additive robustness dimensions for the 2026-10-07 delivery.

The eight gates in ``configs/validation_gates.yaml`` are frozen: thresholds,
split and cost assumptions are not to be touched. This module therefore adds
**new, strictly stricter** dimensions in a separate layer rather than editing
any existing gate logic.

Adding stricter evidence can only remove factors from the delivery set, never
admit one, so it cannot be a way of passing a gate that would otherwise fail.
That property is the whole reason this is allowed to exist next to a frozen
config, and it is asserted by a test.

Three dimensions, all requested by the client-facing methodology:

``benjamini_hochberg``
    Multiple-testing correction across the whole candidate batch. Running ~900
    factors at p < 0.05 and reporting the survivors is a false-discovery
    machine; BH-FDR controls the expected proportion of false discoveries.
    This is inherently a *batch* statistic, which is why it cannot be a
    per-factor gate.

``industry_neutral_ic``
    The frozen ``style_r2`` gate residualises the factor on
    size/momentum/volatility/liquidity but has **no industry term**, so a factor
    that is pure industry exposure can pass it. This computes IC after removing
    within-date industry means.

``excess_ic``
    The frozen gates evaluate absolute long-short return; no benchmark is
    consulted anywhere. This recomputes IC against forward returns net of the
    benchmark's own forward return over the same horizon.

Read-only with respect to the repository: nothing here writes a file.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np
import pandas as pd

__all__ = [
    "BenjaminiHochbergResult",
    "benjamini_hochberg",
    "demean_within_groups",
    "excess_forward_returns",
    "forward_returns",
    "industry_neutral_ic",
    "ic_series",
    "summarize_ic",
]


# ── multiple testing ────────────────────────────────────────────────────

@dataclass(frozen=True)
class BenjaminiHochbergResult:
    """Outcome of a Benjamini-Hochberg FDR control at level ``q``."""

    accepted: tuple[bool, ...]
    adjusted: tuple[float, ...]
    q: float
    n_submitted: int
    n_tested: int
    n_accepted: int

    @property
    def n_rejected(self) -> int:
        return self.n_tested - self.n_accepted

    def as_dict(self) -> dict[str, Any]:
        return {
            "q": self.q,
            "n_submitted": self.n_submitted,
            "n_tested": self.n_tested,
            "n_accepted": self.n_accepted,
            "n_rejected": self.n_rejected,
        }


def benjamini_hochberg(p_values: Iterable[float], q: float = 0.05) -> BenjaminiHochbergResult:
    """Benjamini-Hochberg step-up FDR control.

    Returns the acceptance mask and the adjusted p-values, both aligned with the
    input order. A NaN p-value means the factor could not be tested; it is never
    accepted and does not inflate the number of hypotheses, so it cannot dilute
    the correction for the factors that were tested.

    The adjusted value is the usual ``min over k>=rank of (n/k * p_(k))``,
    enforced monotone.
    """
    if not 0.0 < q < 1.0:
        raise ValueError(f"q must lie strictly between 0 and 1, got {q!r}")

    values = np.asarray(list(p_values), dtype=float)
    if values.ndim != 1:
        raise ValueError("p_values must be one-dimensional")
    n_submitted = int(values.size)
    if n_submitted == 0:
        return BenjaminiHochbergResult((), (), q, 0, 0, 0)
    if np.any((values < 0.0) | (values > 1.0)):
        raise ValueError("p_values must lie in [0, 1]")

    accepted = np.zeros(n_submitted, dtype=bool)
    adjusted = np.full(n_submitted, np.nan, dtype=float)

    testable = np.flatnonzero(np.isfinite(values))
    n_tested = int(testable.size)
    if n_tested == 0:
        return BenjaminiHochbergResult(
            tuple(False for _ in range(n_submitted)),
            tuple(float(v) for v in adjusted),
            q,
            n_submitted,
            0,
            0,
        )

    # Sort only the testable hypotheses, and carry their original positions.
    order = testable[np.argsort(values[testable], kind="stable")]
    ranked = values[order]
    ranks = np.arange(1, n_tested + 1, dtype=float)

    scaled = ranked * n_tested / ranks
    # Enforce monotonicity from the largest p-value downwards.
    monotone = np.minimum.accumulate(scaled[::-1])[::-1]
    adjusted[order] = np.clip(monotone, 0.0, 1.0)

    # Benjamini-Hochberg is a STEP-UP procedure: find the largest k whose
    # p-value clears k*q/m, then reject every hypothesis ranked at or below k.
    # Testing each rank independently is not the same rule -- it can accept a
    # rank while rejecting a lower-ranked hypothesis with an identical p-value,
    # producing a mask that is not even a prefix of the sorted p-values.
    thresholds = q * ranks / n_tested
    clearing = np.flatnonzero(ranked <= thresholds)
    if clearing.size:
        k_star = int(clearing[-1]) + 1
        accepted[order[:k_star]] = True

    return BenjaminiHochbergResult(
        accepted=tuple(bool(v) for v in accepted),
        adjusted=tuple(float(v) for v in adjusted),
        q=q,
        n_submitted=n_submitted,
        n_tested=n_tested,
        n_accepted=int(accepted.sum()),
    )


# ── forward returns ─────────────────────────────────────────────────────

def forward_returns(
    frame: pd.DataFrame,
    *,
    horizon: int,
    price_col: str = "close",
    date_col: str = "date",
    code_col: str = "code",
) -> pd.Series:
    """Simple forward return over ``horizon`` bars, aligned to the frame index."""
    ordered = frame.sort_values([code_col, date_col])
    grouped = ordered.groupby(code_col, sort=False)[price_col]
    forward = grouped.shift(-horizon) / ordered[price_col] - 1.0
    return forward.reindex(frame.index)


def excess_forward_returns(
    returns: pd.Series,
    dates: pd.Series,
    benchmark_forward: pd.Series,
) -> pd.Series:
    """Subtract the benchmark's own forward return, matched on date.

    ``benchmark_forward`` is indexed by date and must already be a forward return
    over the same horizon; this function does no shifting of its own.
    """
    aligned = pd.Series(dates).map(benchmark_forward)
    return returns - aligned.to_numpy()


# ── cross-sectional IC ──────────────────────────────────────────────────

def demean_within_groups(
    values: pd.Series,
    dates: pd.Series,
    groups: pd.Series,
) -> pd.Series:
    """Cross-sectionally demean ``values`` within each (date, group) cell.

    Regressing on a saturated set of group dummies with an intercept leaves
    exactly this residual, so demeaning *is* the industry-neutralisation step --
    no least-squares needed.
    """
    working = pd.DataFrame(
        {
            "value": pd.Series(values).to_numpy(dtype=float),
            "_date": pd.Series(dates).to_numpy(),
            "_group": pd.Series(groups).to_numpy(),
        }
    )
    means = working.groupby(["_date", "_group"], dropna=False)["value"].transform("mean")
    residual = working["value"] - means
    residual.index = pd.Series(values).index
    return residual


def ic_series(
    factor: pd.Series,
    returns: pd.Series,
    dates: pd.Series,
    *,
    minimum_cross_section: int = 20,
    method: str = "spearman",
) -> pd.Series:
    """Per-date cross-sectional correlation between factor and return."""
    working = pd.DataFrame(
        {
            "factor": pd.Series(factor).to_numpy(dtype=float),
            "return": pd.Series(returns).to_numpy(dtype=float),
            "_date": pd.Series(dates).to_numpy(),
        }
    ).dropna()
    if working.empty:
        return pd.Series(dtype=float)

    values: dict[Any, float] = {}
    for date, group in working.groupby("_date", sort=True):
        if len(group) < minimum_cross_section:
            continue
        if group["factor"].nunique() < 2 or group["return"].nunique() < 2:
            continue
        values[date] = float(group["factor"].corr(group["return"], method=method))
    return pd.Series(values, dtype=float).sort_index()


def summarize_ic(series: pd.Series, *, ddof: int = 1) -> dict[str, Any]:
    """Mean / IC_IR / t-stat / day count for an IC series."""
    clean = series.replace([np.inf, -np.inf], np.nan).dropna()
    n = int(len(clean))
    if n == 0:
        return {"mean": float("nan"), "ic_ir": float("nan"), "t_stat": float("nan"), "days": 0}
    mean = float(clean.mean())
    std = float(clean.std(ddof=ddof)) if n > ddof else float("nan")
    ic_ir = mean / std if std and std > 0 else float("nan")
    t_stat = mean / (std / np.sqrt(n)) if std and std > 0 else float("nan")
    return {"mean": mean, "ic_ir": float(ic_ir), "t_stat": float(t_stat), "days": n}


# ── the two client-facing dimensions ────────────────────────────────────

def industry_neutral_ic(
    frame: pd.DataFrame,
    *,
    factor_col: str,
    return_col: str,
    industry_col: str = "industry",
    date_col: str = "date",
    minimum_cross_section: int = 20,
    neutralize_returns: bool = False,
    method: str = "spearman",
    ddof: int = 1,
) -> dict[str, Any]:
    """IC after removing within-date industry means from the factor.

    ``neutralize_returns=False`` (default) mirrors the frozen ``style_r2`` gate's
    convention, which residualises the *factor* and leaves returns alone. Setting
    it to ``True`` also demeans the returns, which is stricter: it asks whether
    the factor explains anything the industry has not already explained.

    Returns a summary dict plus the ``retention`` of the neutral IC against the
    raw IC, which is the number the client actually reads.
    """
    required = {factor_col, return_col, industry_col, date_col}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise KeyError(f"industry_neutral_ic is missing columns: {', '.join(missing)}")

    dates = frame[date_col]
    factor = frame[factor_col].astype(float)
    returns = frame[return_col].astype(float)

    raw = ic_series(
        factor, returns, dates,
        minimum_cross_section=minimum_cross_section, method=method,
    )
    neutral_factor = demean_within_groups(factor, dates, frame[industry_col])
    target = (
        demean_within_groups(returns, dates, frame[industry_col])
        if neutralize_returns
        else returns
    )
    neutral = ic_series(
        neutral_factor, target, dates,
        minimum_cross_section=minimum_cross_section, method=method,
    )

    raw_summary = summarize_ic(raw, ddof=ddof)
    neutral_summary = summarize_ic(neutral, ddof=ddof)
    raw_mean = raw_summary["mean"]
    neutral_mean = neutral_summary["mean"]
    retention = (
        float(neutral_mean / raw_mean)
        if np.isfinite(raw_mean) and np.isfinite(neutral_mean) and abs(raw_mean) > 1e-12
        else float("nan")
    )
    return {
        "raw": raw_summary,
        "neutral": neutral_summary,
        "retention": retention,
        "neutralize_returns": bool(neutralize_returns),
        "industries": int(frame[industry_col].nunique(dropna=True)),
    }


def excess_ic(
    factor: pd.Series,
    returns: pd.Series,
    dates: pd.Series,
    benchmark_returns: pd.Series,
    *,
    minimum_cross_section: int = 20,
    method: str = "spearman",
    ddof: int = 1,
) -> dict[str, Any]:
    """IC against benchmark-excess forward returns.

    ``benchmark_returns`` is indexed by date and describes the benchmark's return
    over the same forward horizon already baked into ``returns``.
    """
    excess = excess_forward_returns(returns, dates, benchmark_returns)
    raw = ic_series(
        factor, returns, dates,
        minimum_cross_section=minimum_cross_section, method=method,
    )
    excess_series = ic_series(
        factor, pd.Series(excess, index=pd.Series(returns).index), dates,
        minimum_cross_section=minimum_cross_section, method=method,
    )
    return {
        "raw": summarize_ic(raw, ddof=ddof),
        "excess": summarize_ic(excess_series, ddof=ddof),
        "ic_series": excess_series,
    }
