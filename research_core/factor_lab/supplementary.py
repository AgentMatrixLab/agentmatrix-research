"""Batch-level supplementary evidence for the 2026-10-07 delivery.

`robustness.py` holds the per-factor mathematics; this module turns those into
the batch-level artefacts the client reads:

* a p-value per factor, taken from the frozen ``rank_ic`` t-statistic,
* Benjamini-Hochberg FDR control across the whole candidate batch,
* the industry-neutral IC retention per factor, when a panel is available.

Nothing here writes to the frozen pipeline or to ``validation_result.json``.
It reads those results and emits a separate supplementary report, so a factor's
``result_hash`` remains exactly what the frozen validator computed.

Read-only: the functions never mutate their inputs.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from research_core.factor_lab.robustness import (
    benjamini_hochberg,
    industry_neutral_ic,
)
from research_core.factor_lab.validation_result import (
    ValidationResultError,
    extract_rank_ic_statistic,
    resolve_primary_horizon,
)

__all__ = [
    "SupplementaryError",
    "build_supplementary_report",
    "industry_neutral_retention",
    "p_value_from_t",
    "rank_ic_t_stat",
]


class SupplementaryError(ValueError):
    """Raised when a validation result cannot yield a testable statistic."""


def p_value_from_t(t_stat: float, degrees_of_freedom: int) -> float:
    """Two-sided Student-t p-value.

    A factor with too few daily observations to define a t-statistic has no
    p-value: it returns NaN, and `benjamini_hochberg` then treats it as
    untestable rather than as evidence.

    scipy is a declared dependency (`requirements-factor-lab.txt`). If it is
    missing we raise rather than fall back to a normal approximation: the
    approximation is anti-conservative in the tail (0.0473 against an exact
    0.0500 at t=1.984, dof=100), which would inflate every discovery count.
    """
    if degrees_of_freedom < 1:
        return float("nan")
    if not math.isfinite(t_stat):
        return float("nan")
    try:
        from scipy import stats  # noqa: PLC0415 - imported lazily for speed
    except ImportError as exc:  # pragma: no cover - scipy is a declared dependency
        raise SupplementaryError(
            "scipy is required for exact Student-t p-values but is not installed. "
            "Install it (pip install 'scipy>=1.14') rather than accepting a normal "
            "approximation, which would overstate significance."
        ) from exc
    return float(2.0 * stats.t.sf(abs(t_stat), degrees_of_freedom))


def rank_ic_t_stat(
    result: Mapping[str, Any],
    *,
    primary_horizon: int | None = None,
) -> tuple[float, int]:
    """Pull (t_stat, days) for the primary horizon out of a validation result.

    The frozen validator keys rank-IC statistics as ``"10d"``; the resolution
    lives in `validation_result` so this module cannot drift from it.
    """
    horizon = (
        resolve_primary_horizon(result)
        if primary_horizon is None
        else primary_horizon
    )
    try:
        return extract_rank_ic_statistic(result, horizon)
    except ValidationResultError as exc:
        raise SupplementaryError(str(exc)) from exc


def industry_neutral_retention(
    panel: pd.DataFrame,
    *,
    factor_values: pd.Series | None,
    factor_col: str,
    return_col: str,
    industry_col: str = "industry",
    date_col: str = "date",
    neutralize_returns: bool = False,
    minimum_cross_section: int = 20,
) -> dict[str, Any] | None:
    """Industry-neutral IC summary for one factor, or None if it cannot be run.

    Returns None -- never a confident-looking number -- when the inputs cannot
    actually support the calculation. Three cases are refused explicitly:

    * the panel carries no industry column;
    * the factor values do not line up with the panel index (a misaligned join
      silently produces all-NaN or a plausible result computed on a subset);
    * neutralisation removed every usable cross-section, which happens when each
      (date, industry) cell holds too few names to rank.
    """
    if industry_col not in panel.columns:
        return None

    working = panel
    if factor_values is not None:
        supplied = pd.Series(factor_values)
        shared = supplied.index.intersection(panel.index)
        if len(shared) < len(panel) * 0.99:
            # A partial overlap would be scored on a subset the caller did not
            # intend, and a disjoint one would be all NaN. Refuse both.
            return None
        working = panel.copy()
        working[factor_col] = supplied.reindex(panel.index).to_numpy()
    elif factor_col not in panel.columns:
        return None

    working[return_col] = pd.to_numeric(working[return_col], errors="coerce")
    if working[return_col].notna().sum() == 0:
        return None

    try:
        result = industry_neutral_ic(
            working,
            factor_col=factor_col,
            return_col=return_col,
            industry_col=industry_col,
            date_col=date_col,
            minimum_cross_section=minimum_cross_section,
            neutralize_returns=neutralize_returns,
        )
    except (KeyError, ValueError):
        # A factor we cannot neutralise gains no evidence; it must not crash a batch.
        return None

    # Neutralisation that never produced a usable cross-section has not been
    # applied at all; reporting a retention from it would be misleading.
    if int(result["neutral"]["days"]) == 0:
        return None
    return result


def build_supplementary_report(
    results: Sequence[Mapping[str, Any]],
    *,
    q: float = 0.05,
    primary_horizon: int | None = None,
    neutral_ic: Mapping[str, Mapping[str, Any] | None] | None = None,
) -> dict[str, Any]:
    """Combine FDR control and industry-neutral retention into one report.

    Factors whose t-statistic cannot be computed are reported as untestable and
    are never counted as discoveries.
    """
    ids: list[str] = []
    t_stats: list[float] = []
    p_values: list[float] = []

    for result in results:
        factor_id = str(result.get("factor_id", "<unknown>"))
        ids.append(factor_id)
        try:
            t_stat, days = rank_ic_t_stat(result, primary_horizon=primary_horizon)
        except SupplementaryError:
            t_stat, days = float("nan"), 0
        t_stats.append(t_stat)
        p_values.append(p_value_from_t(t_stat, days - 1) if days > 1 else float("nan"))

    fdr = benjamini_hochberg(p_values, q=q)

    factors: list[dict[str, Any]] = []
    for position, factor_id in enumerate(ids):
        neutral = None if neutral_ic is None else neutral_ic.get(factor_id)
        factors.append(
            {
                "factor_id": factor_id,
                "t_stat": t_stats[position],
                "p_value": p_values[position],
                "p_adjusted": fdr.adjusted[position],
                "fdr_accepted": fdr.accepted[position],
                "industry_neutral_ic": neutral,
            }
        )

    # Make the cost of the correction explicit. The frozen `rank_ic` gate screens
    # at |t| >= 1.65, which is a *one-sided* ~5% point; FDR is applied to
    # two-sided p-values, so a factor sitting just above the gate can still lose
    # here. Reporting the gap keeps that from looking like a bug.
    uncorrected = [bool(np.isfinite(p) and p < q) for p in p_values]
    lost = [
        factors[i]["factor_id"]
        for i in range(len(factors))
        if uncorrected[i] and not factors[i]["fdr_accepted"]
    ]

    return {
        "schema_version": 1,
        "q": fdr.q,
        "primary_horizon": primary_horizon,
        "p_value_convention": "two-sided Student-t on the frozen rank_ic t-statistic",
        "summary": fdr.as_dict(),
        "marginal_effect": {
            "passed_uncorrected": int(sum(uncorrected)),
            "passed_fdr": fdr.n_accepted,
            "lost_to_correction": len(lost),
            "lost_factor_ids": lost,
        },
        "factors": factors,
    }


def render_markdown(report: Mapping[str, Any], *, limit: int = 40) -> str:
    """A short human-readable companion to the JSON report."""
    summary = report["summary"]
    marginal = report.get("marginal_effect", {})
    lines = [
        "# 补充稳健性报告（多重检验 + 行业中性）",
        "",
        f"- 多重检验：Benjamini-Hochberg，q = {summary['q']}",
        f"- 提交因子：{summary['n_submitted']}　可检验：{summary['n_tested']}　"
        f"通过 FDR：{summary['n_accepted']}　未通过：{summary['n_rejected']}",
        f"- p 值口径：{report.get('p_value_convention', 'two-sided')}",
    ]
    if marginal:
        lines.extend(
            [
                "",
                f"**校正的代价**：未校正时 p < q 的有 **{marginal['passed_uncorrected']}** 个，"
                f"经 FDR 校正后剩 **{marginal['passed_fdr']}** 个，"
                f"**{marginal['lost_to_correction']}** 个被多重检验拦下。",
                "",
                "> 注意口径差异：冻结门槛 `rank_ic` 用的是 **单侧** |t| ≥ 1.65（约等于单侧 5%），"
                "而 FDR 用的是**双侧** p 值。所以一个刚好越过门槛的因子仍可能在这里被拦下 —— "
                "这是刻意的，不是缺陷。",
            ]
        )
    lines.extend(
        [
            "",
            "> 本报告是**追加证据层**，不修改任何已冻结门槛，也不改动 `validation_result.json`。",
            "> 通过 FDR 是**必要条件而非充分条件**：因子仍需通过全部八道冻结门槛。",
            "",
            "| 因子 | t 值 | p 值 | 校正后 p | FDR | 行业中性留存 |",
            "|---|---:|---:|---:|:--:|---:|",
        ]
    )
    rows = sorted(
        report["factors"],
        key=lambda item: (not item["fdr_accepted"], item["p_adjusted"]),
    )
    for item in rows[:limit]:
        neutral = item.get("industry_neutral_ic")
        retention = "—" if not neutral else f"{neutral['retention']:.3f}"
        adjusted = item["p_adjusted"]
        lines.append(
            f"| `{item['factor_id']}` | {item['t_stat']:.3f} | {item['p_value']:.3g} | "
            f"{adjusted:.3g} | {'✅' if item['fdr_accepted'] else '—'} | {retention} |"
        )
    if len(rows) > limit:
        lines.append("")
        lines.append(f"（共 {len(rows)} 个因子，此处只列前 {limit} 个）")
    return "\n".join(lines) + "\n"
