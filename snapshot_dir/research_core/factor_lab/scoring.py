"""Factor scoring: turn frozen gate results into a sortable score and a tier.

Implements `docs/delivery/2026-10-07-scoring-card.md`. Three properties are
non-negotiable and enforced here rather than promised:

1. **The scorer cannot override a gate.** `score_factor` refuses a result that
   has not passed every frozen gate. The scored set is therefore a subset of the
   validated set by construction. `allow_unvalidated=True` exists for dry runs
   and stamps the output so a diagnostic score can never be mistaken for a
   deliverable one.

2. **The scorer cannot recompute a gate.** It only reads fields the frozen
   validator already wrote. Nothing here re-derives an IC, a t-statistic or a
   portfolio return, so `result_hash` stays authoritative.

3. **Every point traces to a number.** Each dimension reports its raw input, its
   normalised score in [0, 1], its weight and the points it contributed.

A dimension whose input is missing is *dropped and the remaining weights
renormalised*, not scored as zero. Scoring missing data as zero would punish a
factor for the pipeline's gap rather than for its own weakness; the output
records which dimensions were missing and what share of the weight was actually
used, so two factors are only compared on comparable evidence.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

import numpy as np
import pandas as pd

from research_core.factor_lab.validation_result import (
    ValidationResultError,
    resolve_primary_horizon,
    resolve_rank_ic_entry,
)

__all__ = [
    "SCORE_CARD",
    "ScoringError",
    "assign_tier",
    "cluster_factors",
    "score_batch",
    "score_factor",
    "select_representatives",
]

#: Trading days per year divided by the frozen `portfolio.rebalance_stride` of 10.
DEFAULT_PERIODS_PER_YEAR = 25.2

TIER_THRESHOLDS = {"S": 75.0, "A": 55.0, "B": 40.0}


class ScoringError(ValueError):
    """Raised when a factor cannot be scored under the card's rules."""


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return float(min(max(value, low), high))


def _linear(value: float, at_zero: float, at_one: float) -> float:
    """Map ``value`` linearly so it scores 0 at ``at_zero`` and 1 at ``at_one``."""
    if at_one == at_zero:
        raise ValueError("at_zero and at_one must differ")
    return _clamp((value - at_zero) / (at_one - at_zero))


# ── dimension extractors ────────────────────────────────────────────────
#
# Each returns (score in [0,1], raw value) or None when the input is absent.

def _primary_rank_ic(result: Mapping[str, Any], horizon: int) -> Mapping[str, Any] | None:
    """Read the rank-IC entry for a horizon, tolerating the validator's key shape.

    The frozen validator keys horizons as ``"10d"``; resolving that here rather
    than with a bare ``str(horizon)`` lookup is what keeps a scoring run from
    silently finding nothing and scoring every factor on missing data.
    """
    return resolve_rank_ic_entry(result, horizon)


def _ic_strength(result: Mapping[str, Any], horizon: int, **_):
    entry = _primary_rank_ic(result, horizon)
    if not entry:
        return None
    raw = abs(float(entry.get("mean", float("nan"))))
    if not math.isfinite(raw):
        return None
    # |IC| 0.01 is the frozen gate floor; 0.06 is treated as excellent.
    return _linear(raw, 0.01, 0.06), raw


def _ic_stability(result: Mapping[str, Any], horizon: int, **_):
    entry = _primary_rank_ic(result, horizon)
    if not entry:
        return None
    raw = abs(float(entry.get("ic_ir", float("nan"))))
    if not math.isfinite(raw):
        return None
    return _clamp(raw / 1.0), raw


def _ic_t_stat(result: Mapping[str, Any], horizon: int, **_):
    entry = _primary_rank_ic(result, horizon)
    if not entry:
        return None
    raw = abs(float(entry.get("t_stat", float("nan"))))
    if not math.isfinite(raw):
        return None
    return _linear(raw, 1.65, 4.0), raw


def _oos_retention(result: Mapping[str, Any], horizon: int, **_):
    entry = _primary_rank_ic(result, horizon)
    training = result.get("training")
    if not entry or not isinstance(training, Mapping):
        return None
    oos = float(entry.get("mean", float("nan")))
    train = float(training.get("primary_rank_ic_mean", float("nan")))
    if not math.isfinite(oos) or not math.isfinite(train) or abs(train) < 1e-12:
        return None
    # A sign flip is a retention of at most zero, however large the ratio.
    ratio = oos / train
    if ratio <= 0:
        return 0.0, ratio
    if ratio >= 1.0:
        return 1.0, ratio
    if ratio >= 0.7:
        return 0.4 + 0.6 * (ratio - 0.7) / 0.3, ratio
    return 0.4 * ratio / 0.7, ratio


def _cost_resilience(result: Mapping[str, Any], **_):
    """How many multiples of the realised cost drag the gross return covers.

    ``breakeven / actual_cost`` is exactly ``gross / (gross - net)``, which is
    derivable from the frozen portfolio metrics without knowing the rebalance
    stride, so no extra assumption enters.
    """
    portfolio = result.get("portfolio")
    if not isinstance(portfolio, Mapping):
        return None
    gross = float(portfolio.get("gross_annualized", float("nan")))
    net = float(portfolio.get("net_annualized", float("nan")))
    if not math.isfinite(gross) or not math.isfinite(net):
        return None
    drag = gross - net
    if drag <= 0:
        return None
    ratio = gross / drag
    return _clamp(ratio / 3.0), ratio


def _style_residual(result: Mapping[str, Any], **_):
    style = result.get("style")
    if not isinstance(style, Mapping):
        return None
    raw = float(style.get("retention", float("nan")))
    if not math.isfinite(raw):
        return None
    # 0.5 is the frozen residual_ic floor; 1.0 keeps everything.
    return _linear(raw, 0.5, 1.0), raw


def _turnover(result: Mapping[str, Any], *, periods_per_year: float, **_):
    portfolio = result.get("portfolio")
    if not isinstance(portfolio, Mapping):
        return None
    raw = float(portfolio.get("mean_turnover", float("nan")))
    if not math.isfinite(raw):
        return None
    annualised = raw * periods_per_year
    # 2x annualised round-trip turnover is cheap; 12x is expensive.
    return _linear(annualised, 12.0, 2.0), annualised


def _market_segments(result: Mapping[str, Any], horizon: int, **_):
    entry = _primary_rank_ic(result, horizon)
    if not entry:
        return None
    yearly = entry.get("yearly")
    if not isinstance(yearly, Mapping) or not yearly:
        return None
    direction = 1.0 if float(entry.get("mean", 0.0)) >= 0 else -1.0
    means = [
        float(item.get("mean", float("nan")))
        for item in yearly.values()
        if isinstance(item, Mapping)
    ]
    usable = [value for value in means if math.isfinite(value)]
    if not usable:
        return None
    agreeing = sum(1 for value in usable if value * direction > 0)
    return agreeing / len(usable), agreeing / len(usable)


def _capacity(result: Mapping[str, Any], *, capacity: float | None, **_):
    if capacity is None or not math.isfinite(capacity) or capacity <= 0:
        return None
    # Log scale: 100M is the floor, 5bn saturates.
    return _clamp(math.log10(capacity / 1e8) / math.log10(5e9 / 1e8)), capacity


def _library_increment(result: Mapping[str, Any], *, library_correlation: float | None, **_):
    if library_correlation is None or not math.isfinite(library_correlation):
        return None
    price = abs(float(library_correlation))
    # At or above the redundancy threshold the factor adds nothing new.
    return _clamp((0.7 - price) / 0.7), price


@dataclass(frozen=True)
class Dimension:
    name: str
    weight: float
    extractor: Callable[..., tuple[float, Any] | None]
    label: str


SCORE_CARD: tuple[Dimension, ...] = (
    Dimension("ic_stability", 20, _ic_stability, "IC 稳定性 (ICIR)"),
    Dimension("ic_strength", 15, _ic_strength, "IC 强度"),
    Dimension("oos_retention", 15, _oos_retention, "样本外留存"),
    Dimension("ic_t_stat", 10, _ic_t_stat, "IC t 值"),
    Dimension("cost_resilience", 10, _cost_resilience, "成本韧性"),
    Dimension("style_residual", 10, _style_residual, "风格残差留存"),
    Dimension("turnover", 8, _turnover, "换手率"),
    Dimension("capacity", 5, _capacity, "容量"),
    Dimension("market_segments", 5, _market_segments, "市场分段一致性"),
    Dimension("library_increment", 2, _library_increment, "库内增量"),
)

TOTAL_WEIGHT = sum(dimension.weight for dimension in SCORE_CARD)


def assign_tier(composite: float, *, truth_verified: bool = False) -> str:
    """Map a composite score onto a delivery tier."""
    if not math.isfinite(composite):
        return "C"
    if truth_verified and composite >= TIER_THRESHOLDS["S"]:
        return "S"
    if composite >= TIER_THRESHOLDS["A"]:
        return "A"
    if composite >= TIER_THRESHOLDS["B"]:
        return "B"
    return "C"


def score_factor(
    result: Mapping[str, Any],
    *,
    horizon: int | None = None,
    periods_per_year: float = DEFAULT_PERIODS_PER_YEAR,
    capacity: float | None = None,
    library_correlation: float | None = None,
    truth_verified: bool = False,
    allow_unvalidated: bool = False,
) -> dict[str, Any]:
    """Score one factor against the card.

    Refuses a result that failed any frozen gate unless ``allow_unvalidated`` is
    set, in which case the output is stamped ``diagnostic_only``.
    """
    factor_id = str(result.get("factor_id", "<unknown>"))
    failed = list(result.get("failed_gates") or [])
    if failed and not allow_unvalidated:
        raise ScoringError(
            f"{factor_id} failed frozen gates {failed} and cannot be scored. "
            "The scorer ranks passers; it does not rescue failures."
        )

    if horizon is None:
        horizon = resolve_primary_horizon(result)

    context = {
        "horizon": horizon,
        "periods_per_year": periods_per_year,
        "capacity": capacity,
        "library_correlation": library_correlation,
    }

    detail: list[dict[str, Any]] = []
    available_weight = 0.0
    awarded = 0.0
    missing: list[str] = []

    try:
        for dimension in SCORE_CARD:
            outcome = dimension.extractor(result, **context)
            if outcome is None:
                missing.append(dimension.name)
                continue
            value, raw = outcome
            value = _clamp(float(value))
            points = value * dimension.weight
            available_weight += dimension.weight
            awarded += points
            detail.append(
                {
                    "name": dimension.name,
                    "label": dimension.label,
                    "weight": dimension.weight,
                    "raw": raw,
                    "score": value,
                    "points": points,
                }
            )
    except ValidationResultError as exc:
        # Structurally unreadable result: list it rather than scoring it on
        # whatever happened to be readable.
        raise ScoringError(str(exc)) from exc

    if available_weight <= 0:
        composite = float("nan")
    else:
        composite = awarded * TOTAL_WEIGHT / available_weight

    payload = {
        "factor_id": factor_id,
        "composite": composite,
        "tier": assign_tier(composite, truth_verified=truth_verified),
        "truth_verified": bool(truth_verified),
        "diagnostic_only": bool(allow_unvalidated or failed),
        "failed_gates": failed,
        "horizon": horizon,
        "weight_available": available_weight,
        "weight_coverage": available_weight / TOTAL_WEIGHT,
        "missing_dimensions": missing,
        "dimensions": detail,
        "source_result_hash": result.get("result_hash"),
    }
    return payload


def score_batch(
    results: Sequence[Mapping[str, Any]],
    *,
    horizon: int | None = None,
    periods_per_year: float = DEFAULT_PERIODS_PER_YEAR,
    capacities: Mapping[str, float] | None = None,
    library_correlations: Mapping[str, float] | None = None,
    truth_verified: Mapping[str, bool] | None = None,
    allow_unvalidated: bool = False,
) -> dict[str, Any]:
    """Score a batch, skipping (and listing) anything that cannot be scored."""
    scored: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []

    for result in results:
        factor_id = str(result.get("factor_id", "<unknown>"))
        try:
            scored.append(
                score_factor(
                    result,
                    horizon=horizon,
                    periods_per_year=periods_per_year,
                    capacity=None if capacities is None else capacities.get(factor_id),
                    library_correlation=(
                        None if library_correlations is None else library_correlations.get(factor_id)
                    ),
                    truth_verified=bool(
                        truth_verified is not None and truth_verified.get(factor_id)
                    ),
                    allow_unvalidated=allow_unvalidated,
                )
            )
        except ScoringError as exc:
            skipped.append({"factor_id": factor_id, "reason": str(exc)})

    scored.sort(key=lambda item: (-(item["composite"] if math.isfinite(item["composite"]) else -1), item["factor_id"]))
    tier_counts: dict[str, int] = {tier: 0 for tier in ("S", "A", "B", "C")}
    for item in scored:
        tier_counts[item["tier"]] += 1

    return {
        "schema_version": 1,
        "horizon": horizon,
        "total_weight": TOTAL_WEIGHT,
        "tier_counts": tier_counts,
        "n_scored": len(scored),
        "n_skipped": len(skipped),
        "skipped": skipped,
        "factors": scored,
    }


# ── correlation clustering (Q1 = C) ─────────────────────────────────────

def cluster_factors(
    correlation: pd.DataFrame,
    *,
    threshold: float = 0.7,
) -> dict[str, Any]:
    """Group factors whose |correlation| exceeds ``threshold``.

    Uses average-linkage agglomeration on the distance ``1 - |corr|``, then cuts
    at ``1 - threshold``. The absolute value is deliberate: two factors that are
    strong mirror images carry the same information and must not both be counted
    as independent evidence.
    """
    if not 0.0 < threshold < 1.0:
        raise ValueError(f"threshold must lie strictly between 0 and 1, got {threshold!r}")
    if not correlation.index.equals(correlation.columns):
        raise ScoringError("correlation matrix must have identical index and columns")

    names = list(correlation.index)
    n = len(names)
    if n == 0:
        return {"threshold": threshold, "clusters": [], "n_clusters": 0}

    values = correlation.to_numpy(dtype=float)
    if np.isnan(values).any():
        # An unmeasurable pair is treated as unrelated rather than as correlated,
        # so a data gap cannot silently merge two clusters.
        values = np.nan_to_num(values, nan=0.0)
    values = np.clip(np.abs(values), 0.0, 1.0)
    np.fill_diagonal(values, 1.0)

    # Agglomerative average linkage, implemented directly so behaviour is
    # explicit and testable without an optional scipy dependency.
    members: list[list[int]] = [[i] for i in range(n)]
    distance = 1.0 - values
    cutoff = 1.0 - threshold
    active = list(range(n))

    def average_linkage(a: list[int], b: list[int]) -> float:
        block = distance[np.ix_(a, b)]
        return float(block.mean())

    while len(active) > 1:
        best = None
        for position, left in enumerate(active):
            for right in active[position + 1 :]:
                gap = average_linkage(members[left], members[right])
                if best is None or gap < best[0]:
                    best = (gap, left, right)
        if best is None or best[0] > cutoff:
            break
        _, left, right = best
        members[left] = members[left] + members[right]
        active.remove(right)

    clusters = []
    for index, cluster_id in enumerate(sorted(active, key=lambda item: min(members[item]))):
        indices = sorted(members[cluster_id])
        block = values[np.ix_(indices, indices)]
        off_diagonal = block[~np.eye(len(indices), dtype=bool)]
        clusters.append(
            {
                "cluster_id": f"C{index:03d}",
                "members": [names[i] for i in indices],
                "size": len(indices),
                "mean_intra_correlation": float(off_diagonal.mean()) if off_diagonal.size else float("nan"),
                "max_intra_correlation": float(off_diagonal.max()) if off_diagonal.size else float("nan"),
            }
        )

    clusters.sort(key=lambda item: (-item["size"], item["members"][0]))
    for index, cluster in enumerate(clusters):
        cluster["cluster_id"] = f"C{index:03d}"

    return {"threshold": threshold, "n_clusters": len(clusters), "clusters": clusters}


def select_representatives(
    clusters: Sequence[Mapping[str, Any]],
    scores: Mapping[str, Mapping[str, Any]],
    *,
    turnover: Mapping[str, float] | None = None,
) -> list[dict[str, Any]]:
    """Pick one representative per cluster.

    Order of preference: highest composite, then lowest turnover (cheaper to
    trade), then factor id for determinism.
    """
    representatives: list[dict[str, Any]] = []
    for cluster in clusters:
        members = list(cluster["members"])
        if not members:
            continue
        # A cluster with a single verified member needs no tie-break.
        scored = [member for member in members if member in scores]

        def rank_key(member: str):
            entry = scores.get(member)
            composite = -1.0
            if entry is not None and math.isfinite(entry.get("composite", float("nan"))):
                composite = float(entry["composite"])
            cost = float("inf")
            if turnover is not None and member in turnover and math.isfinite(turnover[member]):
                cost = float(turnover[member])
            return (-composite, cost, member)

        pool = scored or members
        chosen = min(pool, key=rank_key)
        representatives.append(
            {
                "cluster_id": cluster.get("cluster_id"),
                "representative": chosen,
                "size": cluster.get("size", len(members)),
                "members": members,
                "mean_intra_correlation": cluster.get("mean_intra_correlation"),
                "scored_members": len(scored),
            }
        )
    return representatives
