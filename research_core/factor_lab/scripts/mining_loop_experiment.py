"""W10-W11 因子挖掘闭环实验

Simulates 2-round auto-mine → verify → feedback loop.
Runs on stub/demo data — full IC evaluation requires Qlib + OpenAI.

Usage:
    cd ~/Desktop/agentmatrix-research
    source .venv/bin/activate
    python research_core/factor_lab/scripts/mining_loop_experiment.py
"""

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from research_core.factor_lab.mining_bridge import (
    batch_verify, feedback_to_miner, feedback_to_prompt, parse_expression,
)

# ── Simulated AI candidates per round ──────────────────────────
# Round 1: "中盘股动量 + 换手率确认" — 模拟 LLM 初次生成
ROUND1_CANDIDATES = [
    ("short_momentum_5",  "Ref($close, 5) / $close - 1"),
    ("med_momentum_20",   "Ref($close, 20) / $close - 1"),
    ("vol_shock",         "$volume / Mean($volume, 20)"),
    ("amplitude_mom",     "(($high - $low) / $close) * ($close / Ref($close, 10) - 1)"),
    ("ranked_mom",        "Rank($close / Ref($close, 20) - 1)"),           # cross-sectional
    ("vol_10d",           "Std(Ref($close, 1) / $close, 10)"),             # volatility of returns
    ("mean_rev_5",        "Mean($close, 5)"),
    ("price_hl_ratio",    "$high / $low"),
    ("corr_price_vol",    "Corr($close, $volume, 20)"),
    ("bad_custom_func",   "CustomMomentumEstimator($close, 30, 0.05)"),   # unparseable
]

# Round 2: after feedback, LLM avoids cross-sectional + bad patterns
ROUND2_CANDIDATES = [
    ("mom_20d",           "Ref($close, 20) / $close - 1"),
    ("mom_60d",           "Ref($close, 60) / $close - 1"),
    ("vol_ratio_10",      "$volume / Mean($volume, 10)"),
    ("std_returns_20",    "Std(Ref($close, 1) / $close, 20)"),
    ("ma_20d",            "Mean($close, 20)"),
    ("delta_10d",         "$close - Ref($close, 10)"),
    ("high_low_spread",   "$high / $low"),
    ("corr_hl_vol",       "Corr($high, $low, 10)"),
]


def make_panel(n_dates: int = 100, n_codes: int = 30, seed: int = 42):
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


def run_round(panel, candidates, round_label):
    names   = [c[0] for c in candidates]
    exprs   = [c[1] for c in candidates]
    results = batch_verify(exprs, panel)
    fb_json = feedback_to_miner(results)
    fb_text = feedback_to_prompt(results)

    print(f"\n{'='*60}")
    print(f"  {round_label}")
    print(f"{'='*60}")
    for i, r in enumerate(results):
        ptype = r.parsed.expr_type.name if r.parsed else "—"
        print(f"  {r.status:12s} {names[i]:25s} {ptype:20s} {exprs[i][:55]}")

    stats = fb_json["batch_summary"]
    print(f"\n  Summary: {stats['total']} candidates → "
          f"{stats['passed']} PASS, {stats['failed']} FAIL, "
          f"{stats['pending_jq']} PENDING_JQ, {stats['nc']} NC")
    return results, fb_json, fb_text


def main():
    panel = make_panel()
    print(f"Demo panel: {panel['date'].nunique()} dates × {panel['code'].nunique()} codes")

    # ── Round 1 ──
    r1_results, r1_fb, r1_text = run_round(panel, ROUND1_CANDIDATES, "Round 1: 中盘股动量 (no feedback)")

    # ── Round 2 (with feedback) ──
    r2_results, r2_fb, r2_text = run_round(panel, ROUND2_CANDIDATES, "Round 2: 中盘股动量 (with feedback)")

    # ── Comparison ──
    print(f"\n{'='*60}")
    print(f"  Round 1 → Round 2 comparison")
    print(f"{'='*60}")
    r1p = r1_fb["batch_summary"]
    r2p = r2_fb["batch_summary"]
    print(f"  PASS rate:         {r1p['passed']}/{r1p['total']} ({100*r1p['passed']/r1p['total']:.0f}%) → {r2p['passed']}/{r2p['total']} ({100*r2p['passed']/r2p['total']:.0f}%)")
    print(f"  FAIL rate:         {r1p['failed']}/{r1p['total']} → {r2p['failed']}/{r2p['total']}")
    print(f"  NC rate:           {r1p['nc']}/{r1p['total']} → {r2p['nc']}/{r2p['total']}")
    print(f"  PENDING_JQ rate:   {r1p['pending_jq']}/{r1p['total']} → {r2p['pending_jq']}/{r2p['total']}")

    # ── Feedback that drove the improvement ──
    print(f"\n  Round 1 feedback injected into Round 2 prompt:")
    for line in r1_text.split("\n")[:8]:
        print(f"    {line}")

    # Export results
    out = {
        "experiment": "中盘股动量 + 换手率确认",
        "panel_shape": {"dates": int(panel["date"].nunique()), "codes": int(panel["code"].nunique())},
        "round1": {
            "candidates": ROUND1_CANDIDATES,
            "summary": r1_fb["batch_summary"],
            "results": [
                {"name": n, "expr": e, "status": r.status}
                for (n, e), r in zip(ROUND1_CANDIDATES, r1_results)
            ],
        },
        "round2": {
            "candidates": ROUND2_CANDIDATES,
            "summary": r2_fb["batch_summary"],
            "results": [
                {"name": n, "expr": e, "status": r.status}
                for (n, e), r in zip(ROUND2_CANDIDATES, r2_results)
            ],
        },
        "feedback_text": r1_text,
    }

    out_path = Path(__file__).resolve().parent / "w10_experiment_results.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"\nResults saved to: {out_path}")


if __name__ == "__main__":
    main()
