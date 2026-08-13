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
    compute_ic,
)
from research_core.factor_lab.inference import (
    bootstrap_ic_confidence_multiple,
    ic_decay_analysis,
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
    cache_dir: Optional[str] = None,
    output_dir: str = "",
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
        auto: If True, auto-select factors when ``factors`` is None.
            If False, ``factors`` must be provided explicitly — otherwise a
            ``ValueError`` is raised (caught by the agent API safe wrapper).
        cache_dir: Where to cache market data.  Empty string falls back to the
            project-runtime default (``runtime/factor_lab/cache``), which is
            shared between Python API, CLI, and the raw pipeline.
        output_dir: Where to write the job JSON + factor frame artifacts.
            Defaults to the factor_lab runtime root (``runtime/factor_lab``).
        workspace: FactorLabWorkspaceConfig or None for default
    """
    t0 = time.time()
    if workspace is None:
        workspace = FactorLabWorkspaceConfig().from_env()

    # Resolve cache_dir:
    #   1. explicit non-empty argument wins;
    #   2. otherwise workspace.resolved_cache_dir() — which by default
    #      returns workspace.runtime_root / "cache", so callers wiring
    #      runtime_root=tmp_path stay contained (no bleed into the real
    #      project tree);
    #   3. resolved_cache_dir() itself has a last-resort fallback so an
    #      empty ``cache_dir=""`` can never become Path("") -> CWD/D:\.
    if cache_dir:
        effective_cache_dir = Path(cache_dir).expanduser().resolve()
    else:
        effective_cache_dir = Path(workspace.resolved_cache_dir())

    # ── Step 1: Auto-fetch data ──────────────────────────────
    effective_cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = str(effective_cache_dir / f"{universe}_{start}_{end}.pkl")

    panel = fetch_real_panel(
        start=start, end=end, universe=universe,
        cache_path=cache_path,
    )
    n_stocks = panel["code"].nunique()
    date_range = f"{panel['date'].min()} → {panel['date'].max()}"

    # ── Step 2: Select factors ───────────────────────────────
    # `auto=False` must be honoured: do not auto-select when the caller did
    # not name any factors. This lets agents opt out of the top-N heuristic.
    if factors is None:
        if not auto:
            raise ValueError(
                "auto=False requires an explicit `factors` list. Either pass "
                "factors=[...] or set auto=True to auto-select the top-N factors."
            )
        if factor_set == "alpha101":
            factors = list(IMPLEMENTED_ALPHA101_FACTORS)[:top_n]
        else:
            # factor_set_specs() returns a *list* of spec objects, not a dict —
            # calling .keys() on it crashes. Extract factor_name from each spec.
            specs = factor_set_specs(factor_set)
            factors = [getattr(s, "factor_name", None) for s in specs][:top_n]
            factors = [name for name in factors if name]
            if not factors:
                raise ValueError(f"No factors resolved for factor_set='{factor_set}'.")

    # ── Step 3: Compute factors ──────────────────────────────
    if factor_set == "alpha101":
        factor_frame = compute_alpha101_factors(panel, factor_names=factors)
    else:
        factor_frame = compute_factor_set(panel, factor_set=factor_set, factor_names=factors)

    # ── Step 4: Forward returns + per-factor IC series ───────
    # compute_forward_returns takes `periods`, not `horizon`. The previous call
    # `compute_forward_returns(panel, horizon=horizon)` raised TypeError.
    panel_with_fwd = panel.copy()
    panel_with_fwd["next_return"] = compute_forward_returns(panel, periods=horizon)

    ic_series_by_factor: dict[str, pd.Series] = {}
    ic_results: dict[str, dict[str, float]] = {}
    for fn in factors:
        if fn not in factor_frame.columns:
            continue
        merged = (
            factor_frame[["date", "code", fn]]
            .merge(panel_with_fwd[["date", "code", "next_return"]],
                   on=["date", "code"], how="inner")
            .dropna(subset=[fn, "next_return"])
        )
        if merged.empty:
            ic_series_by_factor[fn] = pd.Series(dtype=float)
            ic_results[fn] = {"ic_mean": 0.0, "ic_ir": 0.0, "ic_std": 0.0}
            continue
        ic_series = compute_ic(merged, factor_col=fn, return_col="next_return", method="rank")
        ic_series_by_factor[fn] = ic_series
        if len(ic_series) > 0:
            ic_mean = float(ic_series.mean())
            ic_std = float(ic_series.std())
            ic_ir = ic_mean / ic_std if ic_std > 0 else 0.0
        else:
            ic_mean = ic_std = 0.0
            ic_ir = 0.0
        ic_results[fn] = {"ic_mean": ic_mean, "ic_ir": ic_ir, "ic_std": ic_std}

    # ── Step 5: Statistical inference ────────────────────────
    for fn, ic_series in ic_series_by_factor.items():
        if len(ic_series) > 20:
            # bootstrap_ic_confidence_multiple expects {factor_name: IC_series},
            # NOT a list — passing [ic_series] crashed with AttributeError.
            ci = bootstrap_ic_confidence_multiple({fn: ic_series}, n_bootstrap=2000)
            ci_result = ci.get(fn, {})
            decay = ic_decay_analysis(ic_series)
            # ic_decay_analysis returns trend_slope / trend_pvalue /
            # split_difference / first_half_mean — NOT decay_pct / p_value.
            # Derive decay_pct as the fractional IC change from first to second
            # half so it is comparable to the gate's DECAY_MAX_PCT threshold.
            first_half = float(decay.get("first_half_mean", 0)) or 0
            split_diff = float(decay.get("split_difference", 0)) or 0
            decay_pct = (
                split_diff / abs(first_half) if abs(first_half) > 1e-10 else 0.0
            )
            ic_results[fn].update({
                "ic_ci_lower": float(ci_result.get("ci_lower", 0)),
                "ic_ci_upper": float(ci_result.get("ci_upper", 0)),
                "decay_pct": decay_pct,
                "decay_pvalue": float(decay.get("trend_pvalue", 1.0)),
            })

    # ── Step 6: OOS validation ───────────────────────────────
    # The previous code called out_of_sample_split(ic_series) which expects a
    # DataFrame (not a Series) and unpacked its dict return as a tuple — both
    # crashed. out_of_sample_ic_compare needs ≥20 stocks per cross-section.
    # Instead, split the IC time-series chronologically and compute retention.
    oos_results = {}
    for fn, ic_series in ic_series_by_factor.items():
        if len(ic_series) > 40:
            split_idx = int(len(ic_series) * 0.7)
            train_ic = ic_series.iloc[:split_idx]
            test_ic = ic_series.iloc[split_idx:]
            train_mean = float(np.mean(train_ic)) if len(train_ic) > 0 else 0.0
            test_mean = float(np.mean(test_ic)) if len(test_ic) > 0 else 0.0
            oos_retention = (
                test_mean / train_mean if abs(train_mean) > 1e-10 else 0.0
            )
            oos_results[fn] = {
                "train_ic_mean": train_mean,
                "test_ic_mean": test_mean,
                "oos_retention": oos_retention,
            }

    # ── Step 7: Similarity check ─────────────────────────────
    sim_results = {}
    if len(factors) >= 2:
        try:
            sim_results = find_similar_factors(factor_frame, factors, threshold=0.7)
        except Exception:
            sim_results = {"error": "similarity check failed"}

    # ── Step 8: Validation gates ─────────────────────────────
    gate = ValidationGate()
    all_verdicts = []
    passed_count = 0

    for fn in factors:
        ic_info = ic_results.get(fn, {})
        oos_info = oos_results.get(fn, {})
        verdict = gate.evaluate(
            factor_name=fn,
            ic_mean=ic_info.get("ic_mean", 0),
            ic_ir=ic_info.get("ic_ir", 0),
            ic_std=ic_info.get("ic_std", 0),
            oos_retention=oos_info.get("oos_retention", 0),
            decay_pct=ic_info.get("decay_pct", 0),
        )
        all_verdicts.append(verdict)
        if verdict.passed:
            passed_count += 1

    # ── Step 9: Top factors + overall gate ───────────────────
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
            f"Call build_strategy(validated_run_path=<artifacts.job_path>) on {top_names[0]}",
            f"Explore {factor_set} factors with higher IC_IR",
        ]
    else:
        summary = (
            f"0/{len(factors)} factors passed gates. "
            f"Max |IC| = {max((abs(v.ic_mean) for v in all_verdicts if v.ic_mean), default=0):.4f}. "
            f"Consider expanding universe or trying a different factor family."
        )
        next_actions = [
            "Try alpha158 or custom factors",
            "Expand universe to csi500 or all",
            "Check data quality for stale prices",
        ]

    # ── Step 10: Persist job artifacts ───────────────────────
    # Write a factor_lab job JSON + factor frame CSV so the documented
    # explore → build_strategy flow can run: build_strategy() reads the job
    # JSON's `requested_factors` and `artifacts.factor_frame`.
    library = factor_set_library_name(factor_set)
    job_id = f"explore_{universe}_{factor_set}_{int(t0 * 1000)}"
    artifact_base = Path(output_dir) if output_dir else workspace.runtime_root
    jobs_dir = artifact_base / "jobs"
    frames_dir = artifact_base / "frames"
    jobs_dir.mkdir(parents=True, exist_ok=True)
    frames_dir.mkdir(parents=True, exist_ok=True)

    available_factors = [fn for fn in factors if fn in factor_frame.columns]
    frame_csv = frames_dir / f"{library.lower()}_{job_id}.csv"
    factor_frame[["date", "code", *available_factors]].to_csv(
        frame_csv, index=False, encoding="utf-8"
    )

    job_payload = {
        "job_id": job_id,
        "library": library,
        "factor_set": factor_set,
        "requested_factors": available_factors,
        "universe": universe,
        "n_stocks": int(n_stocks),
        "date_range": date_range,
        "horizon": horizon,
        "start": start,
        "end": end,
        "created_at": now_iso(),
        "gate_summary": {
            "passed": passed_count,
            "total": len(factors),
            "verdict": overall_gate,
        },
        "artifacts": {"factor_frame": str(frame_csv.resolve())},
    }
    job_json_path = jobs_dir / f"{job_id}.json"
    job_json_path.write_text(
        json.dumps(job_payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    elapsed = time.time() - t0

    result = ExploreResult(
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
        report_path=str(job_json_path),
        artifacts={
            "job_path": str(job_json_path.resolve()),
            "factor_frame": str(frame_csv.resolve()),
            "cache_dir": str(effective_cache_dir),
        },
    )
    return result


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

