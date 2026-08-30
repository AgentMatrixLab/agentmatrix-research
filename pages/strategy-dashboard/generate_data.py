"""Generate pages/strategy-dashboard/data/strategies.json

数据来源（三层合并）：
1. factor-db（pages/factor-db-dashboard）— 因子元数据：中文名/分类/公式
2. lifecycle（pages/lifecycle-dashboard）— 原 v1 策略的因子验证闸门证据
3. backtest_results.json（backtest.py 产出）— 简化回测：metrics + 月度净值 + IC

运行顺序：先 python3.11 backtest.py，再 python3.11 generate_data.py
"""

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # repo root
FDB = ROOT / "pages/factor-db-dashboard/data/factors.json"
LIFE_DIR = ROOT / "pages/lifecycle-dashboard/data/factors"
BT = Path(__file__).resolve().parent / "data/backtest_results.json"
OUT = ROOT / "pages/strategy-dashboard/data/strategies.json"

NOW = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

fdb = json.loads(FDB.read_text(encoding="utf-8"))
meta = {x["factor_id"]: x for x in fdb["dictionary"]}

bt = json.loads(BT.read_text(encoding="utf-8")) if BT.exists() else None
bt_results = (bt or {}).get("results", {})


def lifecycle_evidence(name):
    p = LIFE_DIR / f"{name}.json"
    if not p.exists():
        return None
    d = json.loads(p.read_text(encoding="utf-8"))
    gates = []
    for g in d.get("gates", []):
        item = {"gate": g["gate"], "label": g["label"], "desc": g["desc"],
                "passed": g["passed"], "evidence": g.get("evidence", {})}
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


# ═══════════════════ 策略定义 ═══════════════════
# factors: {factor_key: (direction, weight)} — 与 backtest.py 的 STRATEGY_DEFS 对齐
# name / rationale 为展示文案；universe / cost_model 与回测口径一致

COMMON = {
    "universe": "全A（月均成交额 ≥ 2000 万）",
    "rebalance": "monthly",
    "holding_rule": "合成得分 Top50 等权持有，月频调仓",
    "cost_model": "买 0.13% / 卖 0.18%（佣金+印花税+滑点）",
}

STRATEGY_DEFS = [
    # ── v1 原有策略（保留 id，接入回测） ──
    dict(strategy_id="quality_roe_top20_v1",
         strategy_name="ROE 质量多头 Top50",
         factors={"roe_ttm": (1, 1)}, factor_key="roe_ttm",
         rationale="高 ROE 公司盈利质量高，长期跑赢低 ROE 组；经典质量风格暴露。"),
    dict(strategy_id="trend_mom12_1_top30_v1",
         strategy_name="12-1 动量趋势 Top50",
         factors={"momentum_12_1": (1, 1)}, factor_key="momentum_12_1",
         rationale="剔除近月后的 12 月动量在 A 股中长周期上仍有趋势延续性。"),
    dict(strategy_id="low_vol_defensive_v1",
         strategy_name="低波动防御 Bottom50",
         factors={"volatility_1m": (-1, 1)}, factor_key="volatility_1m",
         rationale="低波动异象：低波组长期风险调整后收益优于高波组，回撤显著更小。"),
    dict(strategy_id="contrarian_reversal_v1",
         strategy_name="月度反转超跌买入",
         factors={"reversal": (1, 1)}, factor_key="reversal",
         rationale="A 股月度反转效应：短期超跌组合存在均值回归收益。"),
    dict(strategy_id="alpha101_alpha1_quantile_v1",
         strategy_name="Alpha#1 量价分层多头",
         factors={}, factor_id="ALPHA101:alpha1", no_backtest=True,
         rationale="WorldQuant Alpha#1：负收益日的波动率放大信号，经典量价横截面因子。"),
    # ── 单因子扩容（19 个） ──
    dict(strategy_id="mom_6m_top50_v1",
         strategy_name="6 月动量多头",
         factors={"ret_6m": (1, 1)}, factor_key="ret_6m",
         rationale="中期价格动量：过去 6 月强势股的相对强度延续。"),
    dict(strategy_id="mom_voladj_3m_v1",
         strategy_name="波动率调整动量",
         factors={"ret_3m_vol_adj": (1, 1)}, factor_key="ret_3m_vol_adj",
         rationale="夏普式动量：收益按波动率缩放，剔除高波噪音后的趋势信号。"),
    dict(strategy_id="low_vol_3m_v1",
         strategy_name="3 月低波防御",
         factors={"volatility_3m": (-1, 1)}, factor_key="volatility_3m",
         rationale="3 月窗口波动率最低组合，防御风格；与 1 月低波互为稳健性检验。"),
    dict(strategy_id="illiq_premium_v1",
         strategy_name="Amihud 非流动性溢价",
         factors={"illiquidity": (1, 1)}, factor_key="illiquidity",
         rationale="Amihud（2002）：单位成交额推动的价格变化越大，流动性补偿越高。"),
    dict(strategy_id="low_turnover_v1",
         strategy_name="低换手率",
         factors={"turnover_proxy": (-1, 1)}, factor_key="turnover_proxy",
         rationale="低换手股票持有者结构稳定，投机交易少，长期超额收益来源之一。"),
    dict(strategy_id="low_price_v1",
         strategy_name="低价股因子",
         factors={"log_price": (-1, 1)}, factor_key="log_price",
         rationale="A 股低价股效应：名义价格低 的股票散户偏好驱动的溢价。"),
    dict(strategy_id="rsi_reversal_v1",
         strategy_name="RSI 超卖反转",
         factors={"rsi_14": (-1, 1)}, factor_key="rsi_14",
         rationale="14 日 RSI 最低组合：技术性超卖后的均值回归。"),
    dict(strategy_id="bb_reversal_v1",
         strategy_name="布林带下轨反转",
         factors={"bb_position": (-1, 1)}, factor_key="bb_position",
         rationale="价格处于布林带下轨附近的股票，统计性反弹概率较高。"),
    dict(strategy_id="anti_lottery_v1",
         strategy_name="反彩票偏好",
         factors={"max_ret_1m": (-1, 1)}, factor_key="max_ret_1m",
         rationale="Bali et al.（2011）MAX 效应：近月最大单日涨幅高的彩票型股票被高估。"),
    dict(strategy_id="low_amplitude_v1",
         strategy_name="低振幅防御",
         factors={"amplitude_1m": (-1, 1)}, factor_key="amplitude_1m",
         rationale="日均振幅低的股票波动小、博弈交易少，风险调整后收益占优。"),
    dict(strategy_id="ma_trend_v1",
         strategy_name="均线趋势跟随",
         factors={"ma_signal": (1, 1)}, factor_key="ma_signal",
         rationale="价格相对 20 日均线偏离度：趋势延续的经典技术信号。"),
    dict(strategy_id="quality_roa_v1",
         strategy_name="ROA 质量多头",
         factors={"roa_ttm": (1, 1)}, factor_key="roa_ttm",
         rationale="总资产收益率衡量资产运营效率，与 ROE 互补的质量指标。"),
    dict(strategy_id="quality_margin_v1",
         strategy_name="净利率质量多头",
         factors={"net_margin": (1, 1)}, factor_key="net_margin",
         rationale="销售净利率反映定价权与成本控制能力，盈利质量的核心维度。"),
    dict(strategy_id="growth_rev_v1",
         strategy_name="营收增长多头",
         factors={"revenue_yoy": (1, 1)}, factor_key="revenue_yoy",
         rationale="营收同比增速：成长性因子中质量最高的口径（受会计调整影响最小）。"),
    dict(strategy_id="growth_profit_v1",
         strategy_name="利润增长多头",
         factors={"profit_yoy": (1, 1)}, factor_key="profit_yoy",
         rationale="净利润同比增速：直接成长指标，弹性大于营收。"),
    dict(strategy_id="growth_eps_v1",
         strategy_name="EPS 增长多头",
         factors={"eps_yoy": (1, 1)}, factor_key="eps_yoy",
         rationale="每股收益增速：股东视角的成长，受股本变动影响。"),
    dict(strategy_id="quality_turnover_v1",
         strategy_name="资产周转率多头",
         factors={"asset_turnover": (1, 1)}, factor_key="asset_turnover",
         rationale="杜邦分解第三要素：运营效率因子的横截面选股能力。"),
    dict(strategy_id="low_leverage_v1",
         strategy_name="低杠杆防御",
         factors={"debt_to_asset": (-1, 1)}, factor_key="debt_to_asset",
         rationale="资产负债率最低组合：财务风险溢价 + 防御属性。"),
    dict(strategy_id="small_size_v1",
         strategy_name="小市值（对数成交额）",
         factors={"log_amount_1m": (-1, 1)}, factor_key="log_amount_1m",
         rationale="以对数成交额代理规模：小规模股票的流动性/壳价值溢价。"),
    # ── 多因子组合（3 个） ──
    dict(strategy_id="multi_quality_growth_v1",
         strategy_name="多因子：质量成长复合",
         strategy_type="multi_factor",
         factors={"roe_ttm": (1, 1.0), "net_margin": (1, 0.5),
                  "revenue_yoy": (1, 0.5), "debt_to_asset": (-1, 0.5)},
         rationale="质量（ROE/净利率）+ 成长（营收增速）− 风险（杠杆）的复合得分，四个维度分散单因子噪音。"),
    dict(strategy_id="multi_mom_lowvol_v1",
         strategy_name="多因子：动量低波复合",
         strategy_type="multi_factor",
         factors={"momentum_12_1": (1, 1.0), "ret_3m_vol_adj": (1, 0.5),
                  "volatility_1m": (-1, 0.5)},
         rationale="中期动量 + 波动率调整动量 − 短期波动：趋势与防御的结合。"),
    dict(strategy_id="multi_smart_beta_v1",
         strategy_name="多因子：Smart Beta 五因子",
         strategy_type="multi_factor",
         factors={"roe_ttm": (1, 0.6), "momentum_12_1": (1, 0.4),
                  "revenue_yoy": (1, 0.4), "volatility_3m": (-1, 0.4),
                  "turnover_proxy": (-1, 0.3)},
         rationale="质量 + 动量 + 成长 − 波动 − 换手的五因子复合，机构 Smart Beta 常用风格组合。"),
]


# ═══════════════════ 组装 ═══════════════════

def factor_detail(fkey, direction, weight):
    m = meta[f"QAPI33:{fkey}"]
    return {
        "factor_id": m["factor_id"],
        "name_cn": m["name_cn"],
        "name_en": m.get("name_en", ""),
        "category": m["category"],
        "subcategory": m.get("subcategory", ""),
        "frequency": m.get("frequency", ""),
        "formula_expr": m.get("formula_expr", ""),
        "definition": m.get("definition", ""),
        "direction": "做多高值" if direction > 0 else "做多低值",
        "direction_sign": direction,
        "weight": weight,
    }


def ic_summary_from_backtest(bt_r):
    ic = (bt_r or {}).get("ic")
    if not ic:
        return None
    return {
        "mean_rank_ic": ic.get("mean_rank_ic"),
        "icir": ic.get("icir"),
        "bootstrap_ci95": ic.get("bootstrap_ci95"),
        "n_months": ic.get("n_months"),
        "t_stat": ic.get("t_stat"),
        "ic_positive_ratio": ic.get("ic_positive_ratio"),
    }


def ic_significant(ic_s):
    """IC Bootstrap 95% CI 不含 0 → 显著。"""
    ci = (ic_s or {}).get("bootstrap_ci95")
    return bool(ci and len(ci) == 2 and (ci[0] > 0 or ci[1] < 0))


strategies = []
for sd in STRATEGY_DEFS:
    sid = sd["strategy_id"]
    is_multi = sd.get("strategy_type") == "multi_factor"
    no_bt = sd.get("no_backtest") or not bt_results.get(sid)

    # ── 因子元数据 ──
    if is_multi:
        details = [factor_detail(k, d, w) for k, (d, w) in sd["factors"].items()]
        fmeta = {
            "factor_id": f"MULTI:{sid}",
            "name_cn": f"多因子组合（{len(details)} 因子）",
            "name_en": "multi_factor_composite",
            "category": "多因子组合",
            "subcategory": "复合因子",
            "frequency": "monthly",
            "formula_expr": " + ".join(
                f"{'+' if d > 0 else '-'}{w}×zscore({k})" for k, (d, w) in sd["factors"].items()),
            "definition": "横截面 zscore 加权复合得分，等权 Top50 持仓。",
        }
    elif sd.get("factor_id"):  # ALPHA101（无 factor_monthly 数据）
        m = meta[sd["factor_id"]]
        details = []
        fmeta = {
            "factor_id": m["factor_id"],
            "name_cn": m["name_cn"],
            "name_en": m.get("name_en", ""),
            "category": m["category"],
            "subcategory": m.get("subcategory", ""),
            "frequency": m.get("frequency", ""),
            "formula_expr": m.get("formula_expr", ""),
            "definition": m.get("definition", ""),
        }
    else:
        k = sd["factor_key"]
        details = [factor_detail(k, *sd["factors"][k])]
        fmeta = dict(details[0])
        fmeta.pop("direction", None)
        fmeta.pop("direction_sign", None)
        fmeta.pop("weight", None)

    # ── 回测结果 ──
    bt_r = bt_results.get(sid)
    metrics = (bt_r or {}).get("metrics")
    ic_s = ic_summary_from_backtest(bt_r)

    if no_bt:
        status, status_label = "not_connected", "因子就绪 · 验证待启动"
    elif ic_significant(ic_s):
        status, status_label = "backtest_ready", "回测就绪 · IC 显著"
    else:
        status, status_label = "review_needed", "研究验证 · IC 不显著"

    # ── 生命周期证据（原 v1 策略才有） ──
    ev = lifecycle_evidence(sd["factor_key"]) if sd.get("factor_key") and not is_multi else None
    yearly_ic = None
    if ev:
        for g in ev["gates"]:
            if g["gate"] == "g11_market_segments":
                yearly_ic = g["evidence"].get("yearly_ic")

    s = {
        "strategy_id": sid,
        "strategy_name": sd["strategy_name"],
        "strategy_type": sd.get("strategy_type", "single_factor"),
        "status": status,
        "status_label": status_label,
        "source": "Factor Lab",
        "factors": [f"QAPI33:{k}" for k in sd["factors"]] if sd["factors"] else [sd.get("factor_id", "")],
        "factor_meta": fmeta,
        "factors_detail": details,
        **{k: v for k, v in COMMON.items() if not no_bt},
        "universe": COMMON["universe"] if not no_bt else "中证500 成分",
        "rebalance": "monthly",
        "holding_rule": COMMON["holding_rule"] if not no_bt else "alpha1 值 top 30% 分层多头",
        "cost_model": COMMON["cost_model"] if not no_bt else "commission=0.03%, tax=0.05%, slippage=0.1%",
        "rationale": sd["rationale"],
        "factor_evidence": ev,
        "ic_summary": ic_s,
        "factor_yearly_ic": yearly_ic,
        "metrics": metrics or {"annual_return": None, "sharpe": None,
                               "max_drawdown": None, "turnover": None},
        "backtest": None if no_bt else {
            "method": "等权 Top50 · 月频调仓 · 含交易成本（简化回测）",
            "window": bt.get("backtest_window"),
            "top_n": bt.get("top_n"),
            "universe_rule": bt.get("universe_rule"),
            "cost_model": bt.get("cost_model"),
            "benchmark": {
                "id": "equal_weight_all_a",
                "label": "全A等权基准",
                "annual_return": bt["benchmark"]["metrics"]["annual_return"],
                "sharpe": bt["benchmark"]["metrics"]["sharpe"],
                "max_drawdown": bt["benchmark"]["metrics"]["max_drawdown"],
            },
            "metrics": metrics,
            "nav": bt_r.get("nav"),
        },
        "artifacts": [],
        "updated_at": NOW,
        "note": ("静态快照 · 简化回测口径（等权月频、未剔除 ST/涨跌停），生产级回测待接入 strategy_engine"
                 if not no_bt else
                 "静态快照 · alpha1 因子值数据待拉取，回测未启动"),
    }
    if no_bt:
        s.pop("factors_detail", None)
    strategies.append(s)

doc = {
    "schema_version": "factor_lab_strategy_monitor_v1",
    "generated_at": NOW,
    "data_status": "simplified_backtest",
    "backtest_summary": None if not bt else {
        "window": bt.get("backtest_window"),
        "method": "equal_weight_monthly_rebalance",
        "benchmark_annual_return": bt["benchmark"]["metrics"]["annual_return"],
    },
    "strategies": strategies,
}

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
print(f"written: {OUT} ({len(strategies)} strategies)")
for s in strategies:
    m = s["metrics"]
    ic = s["ic_summary"] or {}
    print(f"  {s['strategy_id']:<32} {s['status_label']:<16} "
          f"年化={m.get('annual_return')} 夏普={m.get('sharpe')} "
          f"IC={ic.get('mean_rank_ic', '—')}")
