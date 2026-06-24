"""W10-W11 因子挖掘反馈闭环实验

Real OpenAI + structural check.  Qlib IC evaluation if available.

Honest about what each step does:
  - Round 1: LLM generates candidates → structural check → feedback text
  - Round 2: LLM regenerates with feedback → structural check
  - IC evaluation: uses QlibFactorLab.mine_expression() if Qlib data available

Usage:
    cd ~/Desktop/agentmatrix-research
    source .venv/bin/activate
    export OPENAI_API_KEY=your_key
    python research_core/factor_lab/scripts/mining_loop_experiment.py
"""

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from research_core.factor_lab.mining_bridge import (
    batch_verify, feedback_to_miner, feedback_to_prompt,
)
from research_core.qlib_lab.auto_factor_miner import (
    AIFactorMiner, _get_llm_config,
)


def make_panel(n_dates: int = 60, n_codes: int = 20, seed: int = 42):
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-06-01", periods=n_dates, freq="B")
    codes = [f"C{i:04d}" for i in range(n_codes)]
    idx = pd.MultiIndex.from_product([dates, codes], names=["date", "code"])
    return pd.DataFrame({
        "open":   rng.uniform(10, 100, len(idx)),
        "high":   rng.uniform(10, 100, len(idx)),
        "low":    rng.uniform(10, 100, len(idx)),
        "close":  rng.uniform(10, 100, len(idx)),
        "volume": rng.uniform(1e4, 1e7, len(idx)),
    }, index=idx).reset_index()


def call_llm(prompt: str, count: int = 5, provider: str = "openai") -> list[dict]:
    """Generate factor candidates via LLM. Uses auto_factor_miner's multi-provider support."""
    from research_core.qlib_lab.factor_miner import QlibFactorLab
    miner = AIFactorMiner(QlibFactorLab())
    candidates = miner.propose_candidates(
        theme="", count=count, feedback="", provider=provider,
    )
    # propose_candidates builds its own prompt from theme+count. We need the raw prompt.
    # Fallback: direct call using resolved config.
    base_url, api_key, model = _get_llm_config(provider)
    if not api_key:
        raise RuntimeError(f"No API key for provider '{provider}'. Set QFACTOR_API_KEY or provider-specific env var.")

    from openai import OpenAI
    client = OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)

    # Try chat completions (works for most providers), fall back to responses API
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
        )
        text = response.choices[0].message.content or ""
    except Exception:
        response = client.responses.create(model=model, input=prompt)
        text = getattr(response, "output_text", "") or ""

    try:
        raw = json.loads(text)
    except json.JSONDecodeError:
        print(f"  WARNING: LLM returned non-JSON, raw: {text[:200]}...")
        return []

    if not isinstance(raw, list):
        return []

    candidates = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        expr = str(item.get("expression", "")).strip()
        if name and expr:
            candidates.append({"name": name, "expression": expr})
    return candidates[:count]


def try_qlib_ic(candidates: list[dict], start: str = "2021-01-01", end: str = "2024-12-31") -> list[dict] | None:
    """Run Qlib IC evaluation.  Returns None if Qlib unavailable."""
    try:
        from research_core.qlib_lab.factor_miner import QlibFactorLab
        from research_core.qlib_lab.runtime import QlibWorkspaceConfig, init_qlib_workspace
    except ImportError:
        print("  (Qlib not installed, skipping IC evaluation)")
        return None

    config = QlibWorkspaceConfig(provider_uri="data/qlib/cn_data", region="cn")
    try:
        init_qlib_workspace(config, require_package=True, require_data=True)
    except RuntimeError as e:
        print(f"  (Qlib data not ready: {e})")
        return None

    lab = QlibFactorLab(config=config)
    results = []
    for c in candidates:
        try:
            r = lab.mine_expression(
                name=c["name"], expression=c["expression"],
                description=c.get("description", ""),
                start_time=start, end_time=end, horizon=5,
                source="ai", author="experiment",
                tags=c.get("tags", []),
            )
            results.append({
                "name": c["name"],
                "ic_mean": r["top_metrics"].get("ic_mean", 0.0),
                "rank_ic_mean": r["top_metrics"].get("rank_ic_mean", 0.0),
                "icir": r["top_metrics"].get("icir", 0.0),
            })
        except Exception as e:
            print(f"  IC eval failed for {c['name']}: {e}")
            results.append({"name": c["name"], "ic_mean": 0.0, "error": str(e)})
    return results


def run():
    panel = make_panel()
    print(f"Panel: {panel['date'].nunique()}d × {panel['code'].nunique()}c\n")

    # ── Round 1: LLM generates without feedback ──
    theme = "中盘股动量确认 + 换手率异常识别"
    print(f"=== Round 1: {theme} ===\n")

    r1_prompt = (
        "You are generating testable qlib factor expressions for A-share research.\n"
        "Return strict JSON as a list. Each element must include keys: "
        "name, expression, description, rationale, tags.\n"
        "Use qlib expression syntax and keep each expression concise.\n"
        "Prefer time-series patterns: Ref, Mean, Std, Corr.\n"
        "Avoid cross-sectional ops: Rank, IndNeutralize, Group, Cut.\n"
        f"Research theme: {theme}\nNumber of candidates: 5"
    )

    try:
        r1_candidates = call_llm(r1_prompt)
        print(f"Generated {len(r1_candidates)} candidates:")
        for c in r1_candidates:
            print(f"  {c['name']}: {c['expression']}")
    except RuntimeError as e:
        print(f"Cannot call OpenAI: {e}")
        return

    # ── Structural check ──
    r1_exprs = [c["expression"] for c in r1_candidates]
    r1_results = batch_verify(r1_exprs, panel)
    print()
    for i, r in enumerate(r1_results):
        ptype = r.parsed.expr_type.name if r.parsed else "—"
        print(f"  {r.status:12s} {r1_candidates[i]['name']:25s} {ptype:20s}")

    # ── Build feedback ──
    r1_feedback = feedback_to_prompt(r1_results)
    print(f"\n  Feedback for Round 2:")
    for line in r1_feedback.split("\n")[:6]:
        print(f"    {line}")

    # ── Round 2: LLM regenerates with feedback ──
    print(f"\n=== Round 2: {theme} (with feedback) ===\n")

    r2_prompt = (
        "You are generating testable qlib factor expressions for A-share research.\n"
        "Return strict JSON as a list. Each element must include keys: "
        "name, expression, description, rationale, tags.\n"
        "Use qlib expression syntax and keep each expression concise.\n"
        "Prefer time-series patterns: Ref, Mean, Std, Corr.\n"
        "Avoid cross-sectional ops: Rank, IndNeutralize, Group, Cut.\n"
        f"\n=== Feedback from previous iteration ===\n{r1_feedback}\n=== End feedback ===\n"
        f"\nResearch theme: {theme}\nNumber of candidates: 5"
    )

    try:
        r2_candidates = call_llm(r2_prompt)
        print(f"Generated {len(r2_candidates)} candidates:")
        for c in r2_candidates:
            print(f"  {c['name']}: {c['expression']}")
    except RuntimeError as e:
        print(f"Cannot call OpenAI: {e}")
        return

    r2_exprs = [c["expression"] for c in r2_candidates]
    r2_results = batch_verify(r2_exprs, panel)
    print()
    for i, r in enumerate(r2_results):
        ptype = r.parsed.expr_type.name if r.parsed else "—"
        print(f"  {r.status:12s} {r2_candidates[i]['name']:25s} {ptype:20s}")

    # ── Comparison ──
    r1_stats = feedback_to_miner(r1_results)["batch_summary"]
    r2_stats = feedback_to_miner(r2_results)["batch_summary"]
    print(f"\n{'='*60}")
    print(f"  Round 1 → Round 2 comparison")
    print(f"{'='*60}")
    print(f"  PARSED:  {r1_stats['parsed']}/{r1_stats['total']} → {r2_stats['parsed']}/{r2_stats['total']}")
    print(f"  NC:      {r1_stats['nc']}/{r1_stats['total']} → {r2_stats['nc']}/{r2_stats['total']}")
    print(f"  PENDING_JQ: {r1_stats['pending_jq']}/{r1_stats['total']} → {r2_stats['pending_jq']}/{r2_stats['total']}")
    print(f"\n  Note: PARSED = structure OK, bridge to jq_gm possible.")
    print(f"  Real GM verification requires registering via expression_to_spec().")

    # ── Qlib IC evaluation (if available) ──
    print(f"\n=== Qlib IC Evaluation ===")
    ic_results = try_qlib_ic(r2_candidates)
    if ic_results:
        for ic in sorted(ic_results, key=lambda x: x.get("ic_mean", 0), reverse=True):
            print(f"  {ic['name']:25s} IC_mean={ic.get('ic_mean', 0):+.4f}  ICIR={ic.get('icir', 0):+.3f}")
    else:
        print("  Skipped — Qlib data not available on this machine.")
        print("  Run on a machine with Qlib cn_data to get IC metrics.")


if __name__ == "__main__":
    run()
