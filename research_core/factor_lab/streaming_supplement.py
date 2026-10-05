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

import warnings
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


#: The panel columns this layer needs. The panel carries ~20; reading all of them costs
#: several GB, and every per-factor call copies the frame, so the waste is paid hundreds of
#: times. Only these four are ever touched.
PANEL_COLUMNS = ("date", "code", "close", "industry")


def prepare_panel(panel_path: str | Path, *, horizon: int) -> pd.DataFrame:
    """Panel sorted by ``(code, date)`` with the forward return the gates use.

    Identical in effect to the previous in-memory preparation, so the neutral IC stays
    comparable to the rehearsal numbers; it simply does not load the other sixteen columns.
    """
    import pyarrow.parquet as pq

    available = set(pq.ParquetFile(panel_path).schema_arrow.names)
    for required in ("date", "code", "close"):
        if required not in available:
            raise StreamingSupplementError(
                f"panel has no `{required}` column; industry-neutral retention cannot be computed"
            )
    columns = [name for name in PANEL_COLUMNS if name in available]
    panel = pd.read_parquet(panel_path, columns=columns)
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


_WORKER_STATE: dict = {}


def _init_worker(panel: pd.DataFrame, positions: np.ndarray, neutralize_returns: bool) -> None:
    """Give each worker the panel once, by fork, instead of pickling it per task.

    The panel is ~3 GB; sending it with every task would cost more than the work.
    """
    _WORKER_STATE.clear()
    _WORKER_STATE["panel"] = panel
    _WORKER_STATE["positions"] = positions
    _WORKER_STATE["neutralize_returns"] = neutralize_returns


def _retention_task(item: tuple[str, np.ndarray]) -> tuple[str, dict | None]:
    from research_core.factor_lab.supplementary import industry_neutral_retention

    factor_id, values = item
    panel = _WORKER_STATE["panel"]
    aligned = pd.Series(np.nan, index=panel.index, dtype=float)
    aligned.iloc[_WORKER_STATE["positions"]] = values
    return factor_id, industry_neutral_retention(
        panel,
        factor_values=aligned,
        factor_col="_factor",
        return_col="forward_return",
        neutralize_returns=_WORKER_STATE["neutralize_returns"],
    )


def neutral_retention_by_factor(
    factor_paths: Sequence[str | Path],
    *,
    panel_path: str | Path,
    horizon: int = 10,
    neutralize_returns: bool = False,
    factor_ids: Iterable[str] | None = None,
    allow_missing: bool = False,
    progress: Callable[[str], None] | None = None,
    jobs: int = 1,
) -> dict[str, dict | None]:
    """Industry-neutral retention per factor, streaming one series at a time.

    ``allow_missing`` decides what happens to a requested factor with no series. The default
    raises, because a silent ``None`` is how a factor ends up delivered with no robustness
    evidence at all. Callers that prefer to report the gap and keep going pass True; either
    way, nothing is ever substituted for a measurement that was not made.

    ``jobs`` spreads the per-factor maths across processes. It is worth having: each factor
    needs two per-date Spearman passes over ~1,600 dates, measured at ~17 s, so 450 factors is
    over two hours single-threaded -- on the critical path, after the shards have stopped.
    The work is GIL-bound and embarrassingly parallel, and forking shares the panel rather than
    copying it. ``jobs=1`` keeps the simple in-process path.
    """
    panel = prepare_panel(panel_path, horizon=horizon)
    wanted = set(factor_ids) if factor_ids is not None else None
    reference = RowOrderReference()
    positions: np.ndarray | None = None
    output: dict[str, dict | None] = {}
    pool = None
    pending: dict = {}
    ctx = None

    if jobs and jobs > 1:
        import multiprocessing

        if "fork" not in multiprocessing.get_all_start_methods():
            # Without fork the ~3 GB panel is pickled to every worker, which costs more than
            # the arithmetic it parallelises. Fall back to the in-process path rather than
            # pretending to parallelise; the deployment target is Linux.
            jobs = 1
        else:
            ctx = multiprocessing.get_context("fork")

    def prepare(series: FactorSeries) -> tuple[str, np.ndarray]:
        nonlocal positions
        if positions is None:
            dates, codes = reference.keys()
            positions = _alignment_index(panel, dates, codes)
            if (positions < 0).any():
                missing = int((positions < 0).sum())
                raise StreamingSupplementError(
                    f"{missing:,} of {len(positions):,} (date, code) rows in the factor values do "
                    "not appear in the panel; aligning them would silently score a subset"
                )
        if len(series.values) != len(positions):
            raise StreamingSupplementError(
                f"factor {series.factor_id!r} has {len(series.values):,} rows but the alignment "
                f"index has {len(positions):,}"
            )
        return series.factor_id, series.values

    try:
        for series in iter_factor_series(factor_paths, reference=reference):
            if wanted is not None and series.factor_id not in wanted:
                continue
            factor_id, values = prepare(series)

            if ctx is None:
                aligned = pd.Series(np.nan, index=panel.index, dtype=float)
                aligned.iloc[positions] = values
                from research_core.factor_lab.supplementary import industry_neutral_retention

                output[factor_id] = industry_neutral_retention(
                    panel,
                    factor_values=aligned,
                    factor_col="_factor",
                    return_col="forward_return",
                    neutralize_returns=neutralize_returns,
                )
            else:
                if pool is None:
                    # The panel and the alignment index are inherited by fork, so they are not
                    # pickled with each task.
                    pool = ctx.Pool(
                        jobs,
                        initializer=_init_worker,
                        initargs=(panel, positions, neutralize_returns),
                    )
                pending[pool.apply_async(_retention_task, ((factor_id, values),))] = factor_id
                if len(pending) >= jobs * 3:
                    for result in pending:
                        key, value = result.get()
                        output[key] = value
                        if progress is not None:
                            progress(key)
                    pending.clear()

            if ctx is None and progress is not None:
                progress(factor_id)

        if pool is not None:
            for result in pending:
                key, value = result.get()
                output[key] = value
                if progress is not None:
                    progress(key)
            pending.clear()
            pool.close()
            pool.join()
    finally:
        if pool is not None:
            pool.terminate()

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
class RankedBlock:
    """Within-date percentile ranks for a set of factors, one column each.

    This is the one structure several post-processing steps need: the redundancy correlation,
    the strategy composite score, and the clustering all start from cross-sectionally ranked
    factor values. Building it once and sharing it is what keeps the chain inside memory.
    """

    ranks: np.ndarray  # float32, shape (rows, factors), NaN where a factor has no value
    dates: np.ndarray  # datetime64[ns] per row
    codes: np.ndarray  # object per row
    factor_ids: list[str]
    factors_missing: list[str]

    @property
    def n_rows(self) -> int:
        return int(self.ranks.shape[0])

    def date_groups(self) -> tuple[np.ndarray, np.ndarray]:
        """Row slices, one per date, after ordering rows by date."""
        order = np.argsort(self.dates, kind="stable")
        ordered = self.dates[order]
        boundaries = np.flatnonzero(ordered[1:] != ordered[:-1]) + 1
        starts = np.concatenate([[0], boundaries])
        ends = np.concatenate([boundaries, [len(ordered)]])
        return order, np.stack([starts, ends], axis=1)


def ranked_block(
    factor_paths,
    *,
    factor_ids: Iterable[str],
    progress: Callable[[str], None] | None = None,
) -> RankedBlock:
    """Stream every factor into one column, then rank within each date.

    Columns follow the order of ``factor_ids`` so a caller can weight them positionally. Peak
    memory is a single float32 array of ``rows x factors`` (about 14 GB at 450 factors and
    7.7M rows); the block is ranked in place, so the raw values are never held alongside it.
    """
    ordered_ids = [str(factor_id) for factor_id in factor_ids]
    column_of = {factor_id: index for index, factor_id in enumerate(ordered_ids)}
    reference = RowOrderReference()
    wide: np.ndarray | None = None
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
        if progress is not None:
            progress(series.factor_id)

    if wide is None:
        return RankedBlock(np.empty((0, 0), dtype=np.float32), np.empty(0), np.empty(0),
                           ordered_ids, ordered_ids)

    dates, codes = reference.keys()
    dates = pd.to_datetime(dates).to_numpy()
    codes = np.asarray(codes, dtype=object)
    block = RankedBlock(wide, dates, codes, ordered_ids,
                        sorted(set(ordered_ids) - seen))

    order = np.argsort(dates, kind="stable")
    ordered = dates[order]
    boundaries = np.flatnonzero(ordered[1:] != ordered[:-1]) + 1
    starts = np.concatenate([[0], boundaries])
    ends = np.concatenate([boundaries, [len(ordered)]])
    for start, end in zip(starts, ends):
        rows = order[start:end]
        block.ranks[rows] = _rank_within_date(wide[rows].astype(np.float64, copy=False))
    return block


def composite_scores(
    block: RankedBlock,
    weights: Mapping[str, float] | None = None,
    columns: Iterable[str] | None = None,
    directions: Mapping[str, float] | None = None,
) -> pd.DataFrame:
    """Mean cross-sectional rank per (date, code) -- the demo's stock score.

    Reproduces `build_strategy_demos.composite_stock_scores` without the pivot: the mean skips
    missing factors, and when weights are supplied the weighted values are averaged over the
    factors actually present rather than renormalised by the weight sum.

    ``directions`` orients each factor before averaging. This is not cosmetic: a factor whose
    training-segment IC is negative predicts a LOW return when its value is high, so buying the
    top of its raw rank trades the wrong side. About half the delivered factors are like this
    (10 of the first 18), and averaging oriented and unoriented ranks together is meaningless.
    The direction comes from the frozen validator's ``training.direction``, which is measured on
    the training split only -- so orienting by it leaks nothing into an out-of-sample backtest.
    """
    if block.n_rows == 0 or not block.factor_ids:
        return pd.DataFrame({"date": [], "code": [], "score": []})

    wanted = None if columns is None else {str(name) for name in columns}
    indices = [
        index
        for index, factor_id in enumerate(block.factor_ids)
        if wanted is None or factor_id in wanted
    ]
    if not indices:
        raise StreamingSupplementError("no factor column was selected for the composite score")

    # Accumulated one column at a time on purpose. Slicing the block (`ranks[:, indices]`) and
    # casting to float64 would materialise 7.7M x n_factors x 8 bytes -- 37 GB at 600 factors,
    # on top of the float32 block itself -- which is an OOM at exactly the moment the delivery is
    # being assembled. One column at a time is 61 MB.
    rows = block.ranks.shape[0]
    total = np.zeros(rows, dtype=np.float64)
    count = np.zeros(rows, dtype=np.int64)
    for index in indices:
        column = block.ranks[:, index].astype(np.float64)
        direction = None if directions is None else directions.get(block.factor_ids[index])
        if direction is not None and float(direction) < 0:
            column = np.where(np.isnan(column), np.nan, 1.0 - column)
        if weights:
            column = column * float(weights.get(block.factor_ids[index], 1.0))
        present = ~np.isnan(column)
        total[present] += column[present]
        count[present] += 1

    with np.errstate(invalid="ignore", divide="ignore"):
        score = np.where(count > 0, total / np.maximum(count, 1), np.nan)
    score[count == 0] = np.nan
    frame = pd.DataFrame(
        {"date": block.dates, "code": block.codes, "score": score}
    ).dropna(subset=["score"])
    return frame.reset_index(drop=True)


def unoriented_factors(
    factor_ids: Iterable[str], directions: Mapping[str, float] | None
) -> list[str]:
    """Factors with no usable direction, which a caller must not silently treat as positive."""
    if not directions:
        return [str(factor_id) for factor_id in factor_ids]
    return [
        str(factor_id)
        for factor_id in factor_ids
        if directions.get(str(factor_id)) is None
    ]


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


def correlation_from_block(block: RankedBlock, *, min_observations: int = 20) -> CorrelationResult:
    """Both correlation statistics for an already-ranked block.

    Split out from `cross_sectional_correlation` so a caller that already holds the ranked
    block -- the strategy demo does -- does not have to read the factor table a second time.
    """
    labels = block.factor_ids
    empty = pd.DataFrame(index=labels, columns=labels, dtype=float)
    if block.n_rows == 0 or block.ranks.shape[1] < 2:
        return CorrelationResult(empty, empty, 0, 0, 0, block.factors_missing)

    wide = block.ranks
    order, slices = block.date_groups()

    factors = wide.shape[1]
    # Two regimes, accumulated separately and combined at the end.
    #
    # A date whose cross-section is complete for every factor needs no pairwise bookkeeping: the
    # counts and sums collapse to scalars, so ONE matrix product suffices. Dates with gaps need
    # the full pairwise set. At the delivery scale most factors have full coverage, so the fast
    # path carries nearly all the weight and cuts the dominant cost by roughly six.
    pooled = {
        "n": np.zeros((factors, factors)),
        "x": np.zeros((factors, factors)),
        "y": np.zeros((factors, factors)),
        "xx": np.zeros((factors, factors)),
        "yy": np.zeros((factors, factors)),
        "xy": np.zeros((factors, factors)),
    }
    complete_rows = 0
    complete_sum = np.zeros(factors)
    complete_sq = np.zeros(factors)
    complete_xy = np.zeros((factors, factors))
    daily_sum = np.zeros((factors, factors))
    daily_count = np.zeros((factors, factors))
    dates_used = dates_skipped = 0

    def _accumulate_daily(per_date: np.ndarray, usable: np.ndarray) -> None:
        daily_sum[:] += np.where(usable, per_date, 0.0)
        daily_count[:] += usable

    for start, end in slices:
        if end - start < min_observations:
            dates_skipped += 1
            continue
        ranks = wide[order[start:end]].astype(np.float64, copy=False)
        present = ~np.isnan(ranks)
        if present.sum() < 2:
            dates_skipped += 1
            continue

        if present.all():
            rows = end - start
            column_sum = ranks.sum(axis=0)
            column_sq = (ranks * ranks).sum(axis=0)
            product = ranks.T @ ranks
            complete_rows += rows
            complete_sum += column_sum
            complete_sq += column_sq
            complete_xy += product

            with np.errstate(invalid="ignore", divide="ignore"):
                mean = column_sum / rows
                covariance = product / rows - np.outer(mean, mean)
                variance = column_sq / rows - mean * mean
                denominator = np.sqrt(np.outer(variance, variance))
                per_date = np.where(denominator > 0, covariance / denominator, np.nan)
            _accumulate_daily(per_date, ~np.isnan(per_date))
        else:
            stats, _mask = _daily_statistics(ranks, present)
            for key, value in stats.items():
                pooled[key] += value
            per_date = _correlation_from(stats)
            usable = (stats["n"] >= min_observations) & ~np.isnan(per_date)
            _accumulate_daily(per_date, usable)
        dates_used += 1

    combined = {
        "n": pooled["n"] + complete_rows,
        "x": pooled["x"] + complete_sum[:, None],
        "y": pooled["y"] + complete_sum[None, :],
        "xx": pooled["xx"] + complete_sq[:, None],
        "yy": pooled["yy"] + complete_sq[None, :],
        "xy": pooled["xy"] + complete_xy,
    }
    pooled_matrix = _correlation_from(combined)
    with np.errstate(invalid="ignore", divide="ignore"):
        daily_matrix = np.where(daily_count > 0, daily_sum / daily_count, np.nan)

    np.fill_diagonal(pooled_matrix, 1.0)
    np.fill_diagonal(daily_matrix, 1.0)
    return CorrelationResult(
        correlation=pd.DataFrame(daily_matrix, index=labels, columns=labels),
        pooled=pd.DataFrame(pooled_matrix, index=labels, columns=labels),
        n_rows=int(wide.shape[0]),
        dates_used=dates_used,
        dates_skipped=dates_skipped,
        factors_missing=block.factors_missing,
    )


def cross_sectional_correlation(
    factor_paths: Sequence[str | Path],
    *,
    factor_ids: Iterable[str],
    progress: Callable[[str], None] | None = None,
    min_observations: int = 20,
) -> CorrelationResult:
    """Daily cross-sectional Spearman between factors, averaged over time."""
    ordered_ids = [str(factor_id) for factor_id in factor_ids]
    block = ranked_block(factor_paths, factor_ids=ordered_ids, progress=progress)
    return correlation_from_block(block, min_observations=min_observations)
