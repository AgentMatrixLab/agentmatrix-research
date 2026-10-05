"""Bounded-memory post-processing over the factor-value long table.

Why this exists
---------------
Three places in the delivery chain used to load the whole factor-value table with
``pd.read_parquet`` and then filter it once per factor:

* ``run_robustness_supplement.py`` — industry-neutral IC per factor,
* ``build_delivery_manifest.py`` — the redundancy clustering,
* ``build_strategy_demos.py`` — the per-stock composite.

At the rehearsal scale (12 factors, ~92M rows) all three worked. At the delivery scale
(~450 delivered factors x 3 series x 7.7M rows, roughly ten billion rows) each one needs more
memory than the machine has, and the per-factor filter rescans the whole table once per
factor. The failure looks like an OOM kill, not a wrong number, so it is at least loud -- but
it only appears at the end of a run, which is the worst time to find it.

What replaces it
----------------
`factor_value_stream` walks the table once and hands back one factor's series at a time. This
module turns that stream into the two statistics the delivery needs:

* `neutral_retention_by_factor` — industry-neutral IC per factor, aligned to the panel by
  ``(date, code)`` exactly as the previous in-memory code did, but holding one series at a
  time instead of the whole table.
* `cross_sectional_correlation` — the redundancy correlation between delivered factors. The
  matrix is built by streaming each factor into one column of a float32 block and then
  accumulating per-date sufficient statistics, so peak memory is ``rows x factors x 4`` bytes
  (about 14 GB at 450 factors) rather than several copies of a float64 pivot.

A note on the statistic
-----------------------
The client-facing methodology (`docs/delivery/methodology.md`) specifies the *daily
cross-sectional* Spearman averaged over time. The implementation this replaces built a dense
pivot and ran one Spearman pooled across every date at once, which mixes the cross-sectional
relationship with time-series co-movement. Both are now produced from the same per-date
accumulators and returned together -- the daily average as the delivered statistic, the
pooled figure alongside it -- so replacing one with the other is a visible, quantified change
rather than a silent one. Correlations are computed pairwise-complete, so a factor with gaps
is not scored against a different universe than its peers.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from research_core.factor_lab.factor_value_stream import (
    FactorSeries,
    RowOrderReference,
    iter_factor_series,
    resolve_factor_paths,
)

__all__ = [
    "StreamingSupplementError",
    "cross_sectional_correlation",
    "neutral_retention_by_factor",
    "prepare_panel",
]


class StreamingSupplementError(RuntimeError):
    """Raised when the streaming layer cannot produce an honest statistic."""


def prepare_panel(panel_path: str | Path, *, horizon: int) -> pd.DataFrame:
    """Panel sorted by ``(code, date)`` with the forward return the gates use.

    Identical in effect to the previous in-memory preparation, so the neutral IC stays
    comparable to the rehearsal numbers.
    """
    panel = pd.read_parquet(panel_path)
    if "industry" not in panel.columns:
        raise StreamingSupplementError(
            "panel has no `industry` column; industry-neutral retention cannot be computed"
        )
    panel = panel.sort_values(["code", "date"]).reset_index(drop=True)
    grouped = panel.groupby("code", sort=False)["close"]
    panel["forward_return"] = grouped.shift(-horizon) / panel["close"] - 1.0
    return panel


def _alignment_index(panel: pd.DataFrame, dates: np.ndarray, codes: np.ndarray) -> np.ndarray:
    """Row positions of ``(date, code)`` pairs in the sorted panel, or -1 when absent."""
    keys = pd.MultiIndex.from_arrays(
        [panel["code"].to_numpy(), pd.to_datetime(panel["date"]).to_numpy()]
    )
    wanted = pd.MultiIndex.from_arrays([codes, pd.to_datetime(dates)])
    return keys.get_indexer(wanted)


def neutral_retention_by_factor(
    factor_paths: Sequence[str | Path],
    *,
    panel_path: str | Path,
    horizon: int = 10,
    neutralize_returns: bool = False,
    factor_ids: Iterable[str] | None = None,
    allow_missing: bool = False,
    progress: Callable[[str], None] | None = None,
) -> dict[str, dict | None]:
    """Industry-neutral retention per factor, streaming one series at a time.

    ``allow_missing`` decides what happens to a requested factor with no series. The default
    raises, because a silent ``None`` is how a factor ends up delivered with no robustness
    evidence at all. Callers that prefer to report the gap and keep going pass True; either
    way, nothing is ever substituted for a measurement that was not made.
    """
    from research_core.factor_lab.supplementary import industry_neutral_retention

    panel = prepare_panel(panel_path, horizon=horizon)
    wanted = set(factor_ids) if factor_ids is not None else None
    reference = RowOrderReference()
    positions: np.ndarray | None = None
    panel_dates = pd.to_datetime(panel["date"]).to_numpy()

    output: dict[str, dict | None] = {}
    for series in iter_factor_series(factor_paths, reference=reference):
        if wanted is not None and series.factor_id not in wanted:
            continue
        if positions is None:
            dates, codes = reference.keys()
            positions = _alignment_index(panel, dates, codes)
            if (positions < 0).any():
                missing = int((positions < 0).sum())
                raise StreamingSupplementError(
                    f"{missing:,} of {len(positions):,} (date, code) rows in the factor values do "
                    "not appear in the panel; aligning them would silently score a subset"
                )
        values = series.values
        if len(values) != len(positions):
            raise StreamingSupplementError(
                f"factor {series.factor_id!r} has {len(values):,} rows but the alignment index "
                f"has {len(positions):,}"
            )
        aligned = pd.Series(np.nan, index=panel.index, dtype=float)
        aligned.iloc[positions] = values
        retention = industry_neutral_retention(
            panel,
            factor_values=aligned,
            factor_col="_factor",
            return_col="forward_return",
            neutralize_returns=neutralize_returns,
        )
        output[series.factor_id] = retention
        if progress is not None:
            progress(series.factor_id)

    if wanted is not None:
        absent = sorted(wanted - set(output))
        if absent:
            message = (
                f"{len(absent)} factor(s) have no series in the factor values, so their "
                f"retention would be missing rather than measured: {absent[:5]}"
            )
            if allow_missing:
                if progress is not None:
                    progress(f"WARNING: {message}")
                for factor_id in absent:
                    output[factor_id] = None
            else:
                raise StreamingSupplementError(message)
    return output


@dataclass
class CorrelationResult:
    """The correlation matrices plus what it took to build them."""

    #: Daily cross-sectional Spearman averaged over dates -- the documented statistic.
    correlation: pd.DataFrame
    #: The previous implementation's statistic: one pooled Spearman over within-date ranks.
    #: Carried so the change is auditable rather than invisible.
    pooled: pd.DataFrame
    n_rows: int
    dates_used: int
    dates_skipped: int
    factors_missing: list[str]

    @property
    def max_pooled_difference(self) -> float:
        """Largest absolute gap between the two statistics, for the run log."""
        if self.correlation.empty or self.pooled.empty:
            return float("nan")
        difference = np.abs(
            self.correlation.to_numpy(dtype=float) - self.pooled.to_numpy(dtype=float)
        )
        return float(np.nanmax(difference)) if np.isfinite(difference).any() else float("nan")


def _rank_within_date(block: np.ndarray) -> np.ndarray:
    """Per-column percentile ranks, NaN preserved.

    Ties share the average rank and NaNs stay NaN, which is what makes the pairwise-complete
    handling below correct rather than merely convenient.
    """
    from scipy import stats

    ranked = stats.rankdata(block, axis=0, nan_policy="omit")
    valid = np.sum(~np.isnan(block), axis=0)
    valid[valid == 0] = 1
    return ranked / valid


def _daily_statistics(
    ranks: np.ndarray, present: np.ndarray
) -> tuple[dict[str, np.ndarray], np.ndarray]:
    """Pairwise sufficient statistics for one date's cross-section of ranks.

    Returns the six accumulators (so the caller can pool them across dates) and the
    pairwise count. Working from accumulators rather than ``np.corrcoef`` is what makes
    pairwise-complete handling exact when a factor has gaps on some names.
    """
    mask = present.astype(np.float64)
    filled = np.where(present, ranks, 0.0)
    squared = filled * filled
    return (
        {
            "n": mask.T @ mask,
            "x": filled.T @ mask,
            "y": mask.T @ filled,
            "xx": squared.T @ mask,
            "yy": mask.T @ squared,
            "xy": filled.T @ filled,
        },
        mask,
    )


def _correlation_from(stats: Mapping[str, np.ndarray]) -> np.ndarray:
    """Pearson correlation from pairwise sufficient statistics."""
    with np.errstate(invalid="ignore", divide="ignore"):
        n = stats["n"]
        mean_x = stats["x"] / n
        mean_y = stats["y"] / n
        covariance = stats["xy"] / n - mean_x * mean_y
        var_x = stats["xx"] / n - mean_x * mean_x
        var_y = stats["yy"] / n - mean_y * mean_y
        denominator = np.sqrt(var_x * var_y)
        return np.where(denominator > 0, covariance / denominator, np.nan)


def cross_sectional_correlation(
    factor_paths: Sequence[str | Path],
    *,
    factor_ids: Iterable[str],
    progress: Callable[[str], None] | None = None,
    min_observations: int = 20,
) -> CorrelationResult:
    """Daily cross-sectional Spearman between factors, averaged over time.

    Peak memory is one float32 block of ``rows x factors`` plus a handful of small
    accumulators; the previous pivot-based implementation needed several float64 copies of a
    much larger frame.
    """
    ordered_ids = [str(factor_id) for factor_id in factor_ids]
    empty = pd.DataFrame(index=ordered_ids, columns=ordered_ids, dtype=float)
    if len(ordered_ids) < 2:
        return CorrelationResult(empty, empty, 0, 0, 0, [])

    column_of = {factor_id: index for index, factor_id in enumerate(ordered_ids)}
    reference = RowOrderReference()
    wide: np.ndarray | None = None
    filled = 0
    seen: set[str] = set()

    for series in iter_factor_series(factor_paths, reference=reference):
        index = column_of.get(series.factor_id)
        if index is None:
            continue
        if wide is None:
            wide = np.full((len(series), len(ordered_ids)), np.nan, dtype=np.float32)
        if len(series) != wide.shape[0]:
            raise StreamingSupplementError(
                f"factor {series.factor_id!r} has {len(series):,} rows, expected {wide.shape[0]:,}"
            )
        wide[:, index] = series.values
        seen.add(series.factor_id)
        filled += 1
        if progress is not None:
            progress(series.factor_id)

    if wide is None or filled < 2:
        return CorrelationResult(empty, empty, 0, 0, 0, sorted(set(ordered_ids) - seen))

    dates, _codes = reference.keys()
    dates = pd.to_datetime(dates).to_numpy()
    order = np.argsort(dates, kind="stable")
    ordered_dates = dates[order]
    boundaries = np.flatnonzero(ordered_dates[1:] != ordered_dates[:-1]) + 1
    starts = np.concatenate([[0], boundaries])
    ends = np.concatenate([boundaries, [len(ordered_dates)]])

    factors = wide.shape[1]
    pooled = {
        "n": np.zeros((factors, factors)),
        "x": np.zeros((factors, factors)),
        "y": np.zeros((factors, factors)),
        "xx": np.zeros((factors, factors)),
        "yy": np.zeros((factors, factors)),
        "xy": np.zeros((factors, factors)),
    }
    daily_sum = np.zeros((factors, factors))
    daily_count = np.zeros((factors, factors))
    dates_used = dates_skipped = 0

    for start, end in zip(starts, ends):
        if end - start < min_observations:
            dates_skipped += 1
            continue
        block = wide[order[start:end]].astype(np.float64, copy=False)
        ranks = _rank_within_date(block)
        present = ~np.isnan(ranks)
        if present.sum() < 2:
            dates_skipped += 1
            continue

        stats, _mask = _daily_statistics(ranks, present)
        for key, value in stats.items():
            pooled[key] += value

        # This date's own correlation, kept separate so the average over dates is available
        # alongside the pooled figure. Both come from the same accumulators, so the extra
        # cost is arithmetic rather than another pass over the data.
        per_date = _correlation_from(stats)
        usable = (stats["n"] >= min_observations) & ~np.isnan(per_date)
        daily_sum += np.where(usable, per_date, 0.0)
        daily_count += usable
        dates_used += 1

    pooled_matrix = _correlation_from(pooled)
    with np.errstate(invalid="ignore", divide="ignore"):
        daily_matrix = np.where(daily_count > 0, daily_sum / daily_count, np.nan)

    np.fill_diagonal(pooled_matrix, 1.0)
    np.fill_diagonal(daily_matrix, 1.0)
    return CorrelationResult(
        correlation=pd.DataFrame(daily_matrix, index=ordered_ids, columns=ordered_ids),
        pooled=pd.DataFrame(pooled_matrix, index=ordered_ids, columns=ordered_ids),
        n_rows=int(wide.shape[0]),
        dates_used=dates_used,
        dates_skipped=dates_skipped,
        factors_missing=sorted(set(ordered_ids) - seen),
    )
