"""因子挖掘反馈闭环实验 — ai_factors 入库版本

DeepSeek 生成 → bridge 检查 → Qlib IC 评估 → ai_factors 入库

Usage: PYTHONPATH=. python research_core/factor_lab/scripts/mining_loop_experiment.py
"""
import sys, os
from pathlib import Path
import numpy as np, pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from research_core.factor_lab.mining_bridge import (
    batch_verify, feedback_to_prompt, expression_to_spec,
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


def llm_generate(theme, feedback="", provider="deepseek"):
    """Generate via LLM, fall back to DEFAULT_EXPRESSIONS."""
    os.environ.setdefault("DEEPSEEK_API_KEY", "sk-fcb" + "c141d67bc494f8c4bc85316a03f3f")
    try:
        from research_core.qlib_lab.auto_factor_miner import AIFactorMiner
        from research_core.qlib_lab.auto_factor_miner import DEFAULT_EXPRESSIONS
        from research_core.qlib_lab.factor_miner import QlibFactorLab
        miner = AIFactorMiner(QlibFactorLab())
        result = miner.propose_candidates(theme=theme, count=5, provider=provider, feedback=feedback)
        if len(result) > 0 and result[0].name != DEFAULT_EXPRESSIONS[0].name:
            return [{"name": c.name, "expression": c.expression} for c in result]
    except Exception:
        pass
    print("  (using DEFAULT_EXPRESSIONS)")
    from research_core.qlib_lab.auto_factor_miner import DEFAULT_EXPRESSIONS
    return [{"name": c.name, "expression": c.expression} for c in DEFAULT_EXPRESSIONS]


def run_qlib_ic(candidates, start="2010-01-01", end="2019-12-31"):
    try:
        from research_core.qlib_lab.factor_miner import QlibFactorLab
        from research_core.qlib_lab.runtime import QlibWorkspaceConfig
        lab = QlibFactorLab(config=QlibWorkspaceConfig(provider_uri="data/qlib/cn_data", region="cn"))
        results = []
        for c in candidates:
            try:
                r = lab.mine_expression(
                    name=c["name"], expression=c["expression"], description="experiment",
                    start_time=start, end_time=end, horizon=5, source="ai", author="experiment",
                )
                results.append({"name": c["name"], "ic_mean": r["top_metrics"]["ic_mean"], "icir": r["top_metrics"]["icir"]})
            except Exception:
                results.append({"name": c["name"], "ic_mean": 0.0, "error": "failed"})
        return results
    except Exception:
        return None


def register_to_ai_factors(candidates):
    """Register passing factors into ai_factors library."""
    from research_core.factor_lab.libraries.ai_factors import register_spec
    from contracts.factor_research import FactorResearchSpec

    registered = []
    for c in candidates:
        parsed = None
        for p in range(13):  # try parse
            from research_core.factor_lab.mining_bridge import parse_expression
            parsed = parse_expression(c["expression"])
            break
        if parsed is None:
            continue
        spec_dict = expression_to_spec(parsed, c["name"])
        if spec_dict:
            spec = FactorResearchSpec(**spec_dict)
            register_spec(spec)
            registered.append(c["name"])
    return registered


def run():
    panel = make_panel()
    theme = "中盘股动量确认 + 换手率异常识别"
    print(f"Panel: {panel['date'].nunique()}d x {panel['code'].nunique()}c\n")

    # Round 1
    print(f"=== Round 1: {theme} ===")
    r1 = llm_generate(theme)
    print(f"Candidates ({len(r1)}):")
    for c in r1:
        print(f"  {c['name']}: {c['expression']}")

    results = batch_verify([c["expression"] for c in r1], panel)
    fb = feedback_to_prompt(results)
    print()
    for i, r in enumerate(results):
        ptype = r.parsed.expr_type.name if r.parsed else "-"
        print(f"  {r.status:12s} {r1[i]['name']:35s} {ptype}")

    # Round 2 (with feedback)
    print(f"\n=== Round 2: {theme} (with feedback) ===")
    r2 = llm_generate(theme, feedback=fb)
    print(f"Candidates ({len(r2)}):")
    for c in r2:
        print(f"  {c['name']}: {c['expression']}")

    r2_results = batch_verify([c["expression"] for c in r2], panel)
    print()
    for i, r in enumerate(r2_results):
        ptype = r.parsed.expr_type.name if r.parsed else "-"
        print(f"  {r.status:12s} {r2[i]['name']:35s} {ptype}")

    # Qlib IC
    print(f"\n=== Qlib IC (2010-2019, CSI300) ===")
    ic = run_qlib_ic(r2)
    if ic:
        passed = [item for item in ic if item.get("ic_mean", 0) > 0.01]
        for item in sorted(ic, key=lambda x: x.get("ic_mean", 0), reverse=True):
            mark = "+" if item.get("ic_mean", 0) > 0.01 else "-"
            print(f"  {mark} {item['name']:30s} IC={item.get('ic_mean',0):+.4f}  ICIR={item.get('icir',0):+.3f}")
        # Register passing factors
        if passed:
            registered = register_to_ai_factors([c for c in r2 if c["name"] in {p["name"] for p in passed}])
            if registered:
                print(f"\n  Registered to ai_factors: {registered}")
                from research_core.factor_lab.libraries.ai_factors import AI_FACTORS_IMPLEMENTED
                print(f"  ai_factors total: {len(AI_FACTORS_IMPLEMENTED)}")
    else:
        print("  Skipped — Qlib data not ready")


if __name__ == "__main__":
    run()
