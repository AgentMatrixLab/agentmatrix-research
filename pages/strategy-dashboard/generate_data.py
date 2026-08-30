"""Generate pages/strategy-dashboard/data/strategies.json
from existing factor metadata (factor-db) + validation evidence (lifecycle)."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # repo root
FDB = ROOT / "pages/factor-db-dashboard/data/factors.json"
LIFE_DIR = ROOT / "pages/lifecycle-dashboard/data/factors"
OUT = ROOT / "pages/strategy-dashboard/data/strategies.json"

fdb = json.loads(FDB.read_text(encoding="utf-8"))
meta = {x["factor_id"]: x for x in fdb["dictionary"]}

def lifecycle_evidence(name):
    p = LIFE_DIR / f"{name}.json"
    if not p.exists():
        return None
    d = json.loads(p.read_text(encoding="utf-8"))
    gates = []
    for g in d.get("gates", []):
        ev = g.get("evidence", {})
        item = {"gate": g["gate"], "label": g["label"], "desc": g["desc"], "passed": g["passed"], "evidence": ev}
        if g.get("reason"):
            item["reason"] = g["reason"]
        gates.append(item)
    return {
        "factor_state": d.get("state"),
        "factor_state_label": d.get("state_label"),
        "passed_all": d.get("passed_all"),
        "n_gates_passed": d.get("n_gates_passed"),
        "n_gates_run": d.get("n_gates_run"),
        "gates": gates,
    }

# 5 个策略：基于因子面板已有因子，覆盖基本面/动量/低波/反转/Alpha101
STRATEGY_DEFS = [
    {
        "strategy_id": "quality_roe_top20_v1",
        "strategy_name": "ROE 质量多头 Top20%",
        "strategy_type": "single_factor",
        "factors": ["QAPI33:roe_ttm"],
        "factor_key": "roe_ttm",
        "universe": "全A（剔除 ST / 上市<1年 / 停牌）",
        "rebalance": "monthly",
        "holding_rule": "因子值 top 20%，等权持有约 50 只",
        "cost_model": "commission=0.03%, tax=0.05%, slippage=0.1%",
        "rationale": "高 ROE 公司盈利质量高，长期跑赢低 ROE 组；经典质量风格暴露。",
    },
    {
        "strategy_id": "trend_mom12_1_top30_v1",
        "strategy_name": "12-1 动量趋势 Top30%",
        "strategy_type": "single_factor",
        "factors": ["QAPI33:momentum_12_1"],
        "factor_key": "momentum_12_1",
        "universe": "中证800 成分",
        "rebalance": "monthly",
        "holding_rule": "动量值 top 30%，等权持有，止损剔除近月反转",
        "cost_model": "commission=0.03%, tax=0.05%, slippage=0.1%",
        "rationale": "剔除近月后的 12 月动量在 A 股中长周期上仍有趋势延续性。",
    },
    {
        "strategy_id": "low_vol_defensive_v1",
        "strategy_name": "低波动防御 Bottom20%",
        "strategy_type": "single_factor",
        "factors": ["QAPI33:volatility_1m"],
        "factor_key": "volatility_1m",
        "universe": "全A（剔除 ST / 日均成交额<3000万）",
        "rebalance": "quarterly",
        "holding_rule": "波动率最低 20%，等权持有，季度再平衡",
        "cost_model": "commission=0.03%, tax=0.05%, slippage=0.1%",
        "rationale": "低波动异象：低波组长期风险调整后收益优于高波组，回撤显著更小。",
    },
    {
        "strategy_id": "contrarian_reversal_v1",
        "strategy_name": "月度反转超跌买入",
        "strategy_type": "single_factor",
        "factors": ["QAPI33:reversal"],
        "factor_key": "reversal",
        "universe": "全A（剔除 ST / 涨跌停不可交易）",
        "rebalance": "monthly",
        "holding_rule": "近月跌幅最深 20% 买入，持有 1 月滚动",
        "cost_model": "commission=0.03%, tax=0.05%, slippage=0.15%",
        "rationale": "A 股月度反转效应：短期超跌组合存在均值回归收益。",
    },
    {
        "strategy_id": "alpha101_alpha1_quantile_v1",
        "strategy_name": "Alpha#1 量价分层多头",
        "strategy_type": "single_factor",
        "factors": ["ALPHA101:alpha1"],
        "factor_key": None,  # ALPHA101 无 lifecycle 验证数据
        "universe": "中证500 成分",
        "rebalance": "monthly",
        "holding_rule": "alpha1 值 top 30% 分层多头",
        "cost_model": "commission=0.03%, tax=0.05%, slippage=0.1%",
        "rationale": "WorldQuant Alpha#1：负收益日的波动率放大信号，经典量价横截面因子。",
    },
]

STATUS_MAP = {
    # (passed_all, has_evidence) -> strategy status
    (True, True): ("backtest_ready", "回测就绪"),
    (False, True): ("review_needed", "研究验证 · 因子未达标"),
    (None, False): ("not_connected", "因子就绪 · 验证待启动"),
}

strategies = []
for sd in STRATEGY_DEFS:
    fid = sd["factors"][0]
    fmeta = meta[fid]
    ev = lifecycle_evidence(sd["factor_key"]) if sd["factor_key"] else None

    if ev is None:
        status, status_label = STATUS_MAP[(None, False)]
    else:
        status, status_label = STATUS_MAP[(ev["passed_all"], True)]

    ic = None
    yearly_ic = None
    if ev:
        for g in ev["gates"]:
            if g["gate"] == "g6_ic_stability":
                e = g["evidence"]
                ic = {
                    "mean_rank_ic": e.get("mean_rank_ic"),
                    "icir": e.get("icir"),
                    "bootstrap_ci95": e.get("bootstrap_ci95"),
                    "n_months": e.get("n_months"),
                }
            if g["gate"] == "g5_executability":
                ic = ic or {}
                ic["raw_ic"] = g["evidence"].get("raw_ic")
                ic["alpha_decay"] = g["evidence"].get("alpha_decay")
            if g["gate"] == "g11_market_segments":
                yearly_ic = g["evidence"].get("yearly_ic")

    s = {
        "strategy_id": sd["strategy_id"],
        "strategy_name": sd["strategy_name"],
        "strategy_type": sd["strategy_type"],
        "status": status,
        "status_label": status_label,
        "source": "Factor Lab",
        "factors": sd["factors"],
        "factor_meta": {
            "factor_id": fid,
            "name_cn": fmeta["name_cn"],
            "name_en": fmeta.get("name_en", ""),
            "category": fmeta["category"],
            "subcategory": fmeta.get("subcategory", ""),
            "frequency": fmeta.get("frequency", ""),
            "formula_expr": fmeta.get("formula_expr", ""),
            "definition": fmeta.get("definition", ""),
        },
        "universe": sd["universe"],
        "rebalance": sd["rebalance"],
        "holding_rule": sd["holding_rule"],
        "cost_model": sd["cost_model"],
        "rationale": sd["rationale"],
        "factor_evidence": ev,
        "ic_summary": ic,
        "factor_yearly_ic": yearly_ic,
        "metrics": {"annual_return": None, "sharpe": None, "max_drawdown": None, "turnover": None},
        "artifacts": [],
        "updated_at": "2026-08-30T00:00:00+08:00",
        "note": "静态快照 · 策略配置就绪，回测指标待接入策略引擎后填充",
    }
    strategies.append(s)

doc = {
    "schema_version": "factor_lab_strategy_monitor_v1",
    "generated_at": "2026-08-30T00:00:00+08:00",
    "data_status": "placeholder",
    "strategies": strategies,
}

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"written: {OUT} ({len(strategies)} strategies)")
for s in strategies:
    ic = s["ic_summary"] or {}
    print(f"  {s['strategy_id']:<34} {s['status_label']:<14} IC={ic.get('mean_rank_ic', '—')} ICIR={ic.get('icir', '—')}")
