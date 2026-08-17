#!/usr/bin/env python3
"""
Agent Pipeline — One-click factor exploration & validation.

The API surface agents actually want:

    from research_core.factor_lab.agent_pipeline import explore
    result = explore(goal="low volatility quality factors",
                     universe="csi300", auto=True)

Returns a structured verdict with red/yellow/green gates.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

from research_core.data_loader.market_data import fetch_real_panel, resolve_universe
from research_core.factor_lab.evaluation import (
    build_alpha101_evaluation_report,
    build_factor_evaluation_report,
    compute_forward_returns,
)
from research_core.factor_lab.inference import (
    bootstrap_ic_confidence_multiple,
    ic_decay_analysis,
    out_of_sample_split,
    out_of_sample_ic_compare,
)
from research_core.factor_lab.libraries.alpha101 import (
    IMPLEMENTED_ALPHA101_FACTORS,
    compute_alpha101_factors,
)
from research_core.factor_lab.libraries.factor_sets import (
    compute_factor_set,
    factor_set_library_name,
    factor_set_specs,
)
from research_core.factor_lab.similarity import find_similar_factors
from research_core.factor_lab.validation_gate import ValidationGate, GateVerdict
from research_core.factor_lab.runtime import FactorLabWorkspaceConfig, now_iso


@dataclass
class ExploreResult:
    """Structured result an agent can parse and act on."""
    goal: str
    universe: str
    n_stocks: int
    date_range: str
    elapsed_seconds: float

    # Factor results
    factors_tested: int
    factors_passed: int
    top_factors: list[dict[str, Any]] = field(default_factory=list)

    # Gate verdict
    gate_verdict: str = "🟡"  # red/yellow/green
    gate_details: dict[str, Any] = field(default_factory=dict)

    # Actionable summary
    summary: str = ""
    next_actions: list[str] = field(default_factory=list)

    # Raw artifacts
    report_path: str = ""
    artifacts: dict[str, Any] = field(default_factory=dict)


def explore(
    goal: str = "",
    universe: str = "csi300",
    factor_set: str = "alpha101",
    factors: Optional[list[str]] = None,
    start: str = "2023-01-01",
    end: str = "2025-12-31",
    horizon: int = 5,
    top_n: int = 10,
    auto: bool = True,
    cache_dir: str = "/tmp/agentmatrix_cache",
    workspace: Optional[FactorLabWorkspaceConfig] = None,
) -> ExploreResult:
    """
    One-click factor exploration pipeline.

    Agents call this with a goal and universe, get back a verdict.

    Args:
        goal: Human-readable goal (e.g. "low volatility quality factors")
        universe: "csi300", "csi500", "all", or list of codes
        factor_set: "alpha101", "wq101", "gtja191", "alpha158"
        factors: Specific factor names, or None for auto
        start/end: Date range
        horizon: Forward return horizon in days
        top_n: How many top factors to report
        auto: If True, auto-fetch data, auto-select factors
        cache_dir: Where to cache market data
        workspace: FactorLabWorkspaceConfig or None for default
    """
    t0 = time.time()
    if workspace is None:
        workspace = FactorLabWorkspaceConfig()

    # ── Step 1: Auto-fetch data ──────────────────────────────
    Path(cache_dir).mkdir(parents=True, exist_ok=True)
    cache_path = f"{cache_dir}/{universe}_{start}_{end}.pkl"

    panel = fetch_real_panel(
        start=start, end=end, universe=universe,
        cache_path=cache_path,
    )
    n_stocks = panel["code"].nunique()
    date_range = f"{panel['date'].min()} → {panel['date'].max()}"

    # ── Step 2: Compute factors ──────────────────────────────
    if factors is None:
        if factor_set == "alpha101":
            factors = list(IMPLEMENTED_ALPHA101_FACTORS)[:top_n]
        else:
            specs = factor_set_specs(factor_set)
            factors = list(specs.keys())[:top_n]

    if factor_set == "alpha101":
        factor_frame = compute_alpha101_factors(panel, factor_names=factors)
    else:
        factor_frame = compute_factor_set(panel, factor_set=factor_set, factor_names=factors)

    # ── Step 3: Evaluate ─────────────────────────────────────
    fwd_rets = compute_forward_returns(panel, horizon=horizon)
    if factor_set == "alpha101":
        eval_report = build_alpha101_evaluation_report(
            factor_frame, fwd_rets, factor_names=factors,
        )
    else:
        eval_report = build_factor_evaluation_report(
            factor_frame, fwd_rets, factor_names=factors,
        )

    # ── Step 4: Statistical inference ────────────────────────
    ic_results = {}
    for fn in factors:
        ic_series = eval_report.get("factor_ic", {}).get(fn, None)
        if ic_series is not None and len(ic_series) > 20:
            ci = bootstrap_ic_confidence_multiple([ic_series], n_bootstrap=2000)
            decay = ic_decay_analysis(ic_series)
            ic_results[fn] = {
                "ic_mean": float(np.mean(ic_series)),
                "ic_ir": float(np.mean(ic_series) / np.std(ic_series)) if np.std(ic_series) > 0 else 0,
                "ic_ci_lower": float(ci[0][0]) if ci else 0,
                "ic_ci_upper": float(ci[0][1]) if ci else 0,
                "decay_pct": float(decay.get("decay_pct", 0)),
                "decay_pvalue": float(decay.get("p_value", 1.0)),
            }

    # ── Step 5: OOS validation ───────────────────────────────
    oos_results = {}
    for fn in factors:
        ic_series = eval_report.get("factor_ic", {}).get(fn, None)
        if ic_series is not None and len(ic_series) > 40:
            train_ic, test_ic = out_of_sample_split(ic_series)
            compare = out_of_sample_ic_compare(train_ic, test_ic)
            oos_results[fn] = {
                "train_ic_mean": float(np.mean(train_ic)),
                "test_ic_mean": float(np.mean(test_ic)),
                "oos_retention": float(compare.get("retention", 0)),
            }

    # ── Step 6: Similarity check ─────────────────────────────
    sim_results = {}
    if len(factors) >= 2:
        try:
            sim_results = find_similar_factors(factor_frame, factors, threshold=0.7)
        except Exception:
            sim_results = {"error": "similarity check failed"}

    # ── Step 7: Validation gates ─────────────────────────────
    gate = ValidationGate()
    all_verdicts = []
    passed_count = 0

    for fn in factors:
        ic_info = ic_results.get(fn, {})
        oos_info = oos_results.get(fn, {})
        ic_mean = ic_info.get("ic_mean", 0)
        ic_ir = ic_info.get("ic_ir", 0)
        oos_ret = oos_info.get("oos_retention", 0)
        decay_pct = ic_info.get("decay_pct", 0)

        verdict = gate.evaluate(
            factor_name=fn,
            ic_mean=ic_mean,
            ic_ir=ic_ir,
            oos_retention=oos_ret,
            decay_pct=decay_pct,
        )
        all_verdicts.append(verdict)
        if verdict.passed:
            passed_count += 1

    # ── Step 8: Build result ─────────────────────────────────
    top_factors = sorted(
        all_verdicts,
        key=lambda v: abs(v.ic_mean) if v.ic_mean else 0,
        reverse=True,
    )[:top_n]

    # Determine overall gate
    if passed_count >= len(factors) * 0.5:
        overall_gate = "🟢"
    elif passed_count >= len(factors) * 0.2:
        overall_gate = "🟡"
    else:
        overall_gate = "🔴"

    # Build summary
    top_names = [v.factor_name for v in top_factors[:5] if v.passed]
    if top_names:
        summary = (
            f"{passed_count}/{len(factors)} factors passed validation gates. "
            f"Top performers: {', '.join(top_names)}. "
            f"Ready for strategy backtest."
        )
        next_actions = [
            f"Run strategy backtest on {top_names[0]}",
            f"Explore {factor_set} factors with higher IC_IR",
        ]
    else:
        summary = (
            f"0/{len(factors)} factors passed gates. "
            f"Max IC_IR = {max((abs(v.ic_mean/v.ic_std) for v in all_verdicts if v.ic_std and v.ic_std > 0), default=0):.2f}. "
            f"Consider expanding universe or trying different factor family."
        )
        next_actions = [
            "Try alpha158 or custom factors",
            "Expand universe to csi500 or all",
            "Check data quality for stale prices",
        ]

    elapsed = time.time() - t0

    return ExploreResult(
        goal=goal or f"auto-explore {factor_set}",
        universe=universe,
        n_stocks=n_stocks,
        date_range=date_range,
        elapsed_seconds=round(elapsed, 1),
        factors_tested=len(factors),
        factors_passed=passed_count,
        top_factors=[
            {
                "name": v.factor_name,
                "ic_mean": round(v.ic_mean, 4) if v.ic_mean else 0,
                "ic_ir": round(v.ic_ir, 2) if v.ic_ir else 0,
                "oos_retention": f"{v.oos_retention:.0%}" if v.oos_retention else "N/A",
                "verdict": "✅ PASS" if v.passed else "❌ FAIL",
                "reasons": v.fail_reasons[:2] if v.fail_reasons else [],
            }
            for v in top_factors
        ],
        gate_verdict=overall_gate,
        gate_details={
            "passed": passed_count,
            "total": len(factors),
            "checks_per_factor": {
                v.factor_name: v.to_dict()
                for v in all_verdicts
            },
        },
        summary=summary,
        next_actions=next_actions,
    )


def explore_to_markdown(result: ExploreResult) -> str:
    """Render an ExploreResult as agent-readable markdown."""
    lines = [
        f"## 🔍 Factor Exploration: {result.goal}",
        f"",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Universe | {result.universe} ({result.n_stocks} stocks) |",
        f"| Date range | {result.date_range} |",
        f"| Factors tested | {result.factors_tested} |",
        f"| Factors passed | {result.factors_passed} |",
        f"| Time | {result.elapsed_seconds}s |",
        f"| Gate | {result.gate_verdict} |",
        f"",
        f"### Top Factors",
        f"",
        f"| Factor | IC Mean | IC_IR | OOS | Verdict |",
        f"|--------|---------|-------|-----|---------|",
    ]
    for f in result.top_factors[:10]:
        lines.append(
            f"| {f['name']} | {f['ic_mean']:.4f} | {f['ic_ir']:.2f} | {f['oos_retention']} | {f['verdict']} |"
        )
    lines.extend([
        f"",
        f"### Summary",
        f"",
        result.summary,
        f"",
        f"### Next Actions",
        f"",
    ])
    for i, action in enumerate(result.next_actions, 1):
        lines.append(f"{i}. {action}")

    return "\n".join(lines)
