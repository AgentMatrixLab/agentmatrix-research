"""因子挖掘反馈闭环实验 — 含 IC 评估

Real Qlib IC evaluation.  OpenAI fallback to DEFAULT_EXPRESSIONS when unavailable.

Usage:
    cd ~/Desktop/agentmatrix-research && source .venv/bin/activate
    PYTHONPATH=. python research_core/factor_lab/scripts/mining_loop_experiment.py
"""
import json, sys, os
from pathlib import Path
import numpy as np, pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from research_core.factor_lab.mining_bridge import (
    batch_verify, feedback_to_miner, feedback_to_prompt,
)

def make_panel(n_dates=60, n_codes=20, seed=42):
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-06-01", periods=n_dates, freq="B")
    codes = [f"C{i:04d}" for i in range(n_codes)]
    idx = pd.MultiIndex.from_product([dates, codes], names=["date", "code"])
    return pd.DataFrame({
        "open": rng.uniform(10,100,len(idx)), "high": rng.uniform(10,100,len(idx)),
        "low": rng.uniform(10,100,len(idx)), "close": rng.uniform(10,100,len(idx)),
        "volume": rng.uniform(1e4,1e7,len(idx)),
    }, index=idx).reset_index()


def get_candidates(round_label, theme, feedback=""):
    """Try OpenAI, fall back to DEFAULT_EXPRESSIONS."""
    try:
        from research_core.qlib_lab.auto_factor_miner import _get_llm_config
        base_url, api_key, model = _get_llm_config("openai")
        if not api_key:
            raise RuntimeError("no API key")

        prompt = (
            "You are generating testable qlib factor expressions. "
            "Return strict JSON list with keys: name, expression. "
            "Prefer time-series: Ref, Mean, Std, Corr. "
            "Avoid: Rank, IndNeutralize, Group, Cut, custom functions.\n"
        )
        if feedback:
            prompt += f"\n=== Feedback ===\n{feedback}\n=== End ===\n"
        prompt += f"\nTheme: {theme}\nCount: 5"

        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)
        try:
            resp = client.chat.completions.create(model=model, messages=[{"role":"user","content":prompt}], temperature=0.7)
            text = resp.choices[0].message.content or ""
        except Exception:
            resp = client.responses.create(model=model, input=prompt)
            text = getattr(resp, "output_text", "") or ""

        raw = json.loads(text) if text else []
        return [{"name": str(item.get("name","")).strip(), "expression": str(item.get("expression","")).strip()}
                for item in raw if isinstance(item, dict) and item.get("name") and item.get("expression")][:5]
    except Exception:
        pass

    print(f"  (OpenAI unavailable, using DEFAULT_EXPRESSIONS)")
    from research_core.qlib_lab.auto_factor_miner import DEFAULT_EXPRESSIONS
    return [{"name": c.name, "expression": c.expression} for c in DEFAULT_EXPRESSIONS]


def run_qlib_ic(candidates, start="2010-01-01", end="2019-12-31"):
    """Run Qlib IC evaluation. Returns list of {name, ic_mean, icir} or None."""
    try:
        from research_core.qlib_lab.factor_miner import QlibFactorLab
        from research_core.qlib_lab.runtime import QlibWorkspaceConfig
        config = QlibWorkspaceConfig(provider_uri="data/qlib/cn_data", region="cn")
        lab = QlibFactorLab(config=config)
    except Exception:
        return None

    results = []
    for c in candidates:
        try:
            r = lab.mine_expression(
                name=c["name"], expression=c["expression"],
                description="experiment", start_time=start, end_time=end,
                horizon=5, source="experiment", author="test",
            )
            results.append({
                "name": c["name"],
                "ic_mean": r["top_metrics"].get("ic_mean", 0.0),
                "icir": r["top_metrics"].get("icir", 0.0),
                "coverage": r["evaluation"].get("coverage", 0),
            })
        except Exception as e:
            results.append({"name": c["name"], "ic_mean": 0.0, "error": str(e)[:60]})
    return results


def run():
    panel = make_panel()
    theme = "中盘股动量确认 + 换手率异常识别"
    print(f"Panel: {panel['date'].nunique()}d x {panel['code'].nunique()}c\n")

    # === Round 1 ===
    print(f"=== Round 1: {theme} ===")
    r1 = get_candidates("R1", theme)
    print(f"Candidates ({len(r1)}):")
    for c in r1:
        print(f"  {c['name']}: {c['expression']}")

    r1_results = batch_verify([c["expression"] for c in r1], panel)
    r1_fb = feedback_to_prompt(r1_results)
    print()
    for i, r in enumerate(r1_results):
        ptype = r.parsed.expr_type.name if r.parsed else "-"
        print(f"  {r.status:12s} {r1[i]['name']:25s} {ptype:20s}")

    # === Round 2 (with feedback) ===
    print(f"\n=== Round 2: {theme} (with feedback) ===")
    r2 = get_candidates("R2", theme, feedback=r1_fb)
    print(f"Candidates ({len(r2)}):")
    for c in r2:
        print(f"  {c['name']}: {c['expression']}")

    r2_results = batch_verify([c["expression"] for c in r2], panel)
    print()
    for i, r in enumerate(r2_results):
        ptype = r.parsed.expr_type.name if r.parsed else "-"
        print(f"  {r.status:12s} {r2[i]['name']:25s} {ptype:20s}")

    # === Comparison ===
    s1 = feedback_to_miner(r1_results)["batch_summary"]
    s2 = feedback_to_miner(r2_results)["batch_summary"]
    print(f"\n{'='*60}")
    print(f"  Structural check")
    print(f"{'='*60}")
    print(f"  PARSED:      {s1['parsed']}/{s1['total']} -> {s2['parsed']}/{s2['total']}")
    print(f"  NC:          {s1['nc']}/{s1['total']} -> {s2['nc']}/{s2['total']}")
    print(f"  PENDING_JQ:  {s1['pending_jq']}/{s1['total']} -> {s2['pending_jq']}/{s2['total']}")

    # === Qlib IC Evaluation ===
    print(f"\n=== Qlib IC Evaluation (2010-2019, CSI300, horizon=5) ===")
    ic = run_qlib_ic(r2)
    if ic:
        for item in sorted(ic, key=lambda x: x.get("ic_mean", 0), reverse=True):
            cov = item.get("coverage", 0)
            print(f"  {item['name']:30s} IC={item.get('ic_mean',0):+.4f}  ICIR={item.get('icir',0):+.3f}  coverage={cov}")
    else:
        print("  Skipped — Qlib data not ready")


if __name__ == "__main__":
    run()
