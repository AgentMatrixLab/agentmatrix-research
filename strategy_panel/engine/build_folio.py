"""
组合策略引擎 — 多策略逆波动率加权合成

方法: 逆波动率加权 (Inverse Volatility Weighting)
  - 对各策略的日收益率计算年化波动率
  - 权重 w_i ∝ 1/σ_i，波动越低权重越大
  - 每日重新平衡到目标权重

输出: D:\bigquant\output\folio.json
"""
import sys, os, json
import numpy as np

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")

# 策略定义
STRATEGIES = [
    {
        "id": "div_v6",
        "json": "dividend_yield_v6.json",
        "name": "红利策略v6(聚宽对齐)",
        "tag": "红利",
    },
    {
        "id": "micro_cap",
        "json": "micro_cap_400.json",
        "name": "微盘股(最小400)",
        "tag": "微盘",
    },
    {
        "id": "supabase",
        "json": "supabase_strategy.json",
        "name": "Supabase信号策略",
        "tag": "信号",
    },
]


def load_nav(json_path):
    """加载策略净值，返回 {date: nav} 和原始 nav 列表"""
    with open(json_path, "r", encoding="utf-8") as f:
        d = json.load(f)
    s = d["strategies"][0] if "strategies" in d else d
    nav_list = s["nav_history"]
    nav_map = {}
    for p in nav_list:
        nav_map[p["date"]] = p["nav"]
    return nav_map, nav_list, s


def compute_inverse_vol_weights(nav_maps):
    """
    计算逆波动率权重。
    对各策略重叠日期区间计算日收益率 → 年化波动率 → 权重 ∝ 1/σ
    """
    # 找到所有策略的重叠日期
    all_dates = sorted(set.intersection(*[set(m.keys()) for m in nav_maps.values()]))
    if len(all_dates) < 20:
        print("  ⚠️ 重叠日期不足，使用等权")
        n = len(nav_maps)
        return {sid: 1.0 / n for sid in nav_maps}

    vols = {}
    for sid, nav_map in nav_maps.items():
        navs = np.array([nav_map[d] for d in all_dates])
        daily_ret = navs[1:] / navs[:-1] - 1
        ann_vol = float(np.std(daily_ret, ddof=1) * np.sqrt(252))
        vols[sid] = ann_vol

    # 逆波动率权重
    inv_vols = {sid: 1.0 / v for sid, v in vols.items() if v > 0}
    total = sum(inv_vols.values())
    weights = {sid: round(w / total, 4) for sid, w in inv_vols.items()}

    print(f"  波动率: {vols}")
    print(f"  逆波动率权重: {weights}")
    return weights


def compute_daily_return_weights(nav_maps):
    """
    备选方案: 等波动率贡献 (Risk Parity 简化版)
    """
    return compute_inverse_vol_weights(nav_maps)


def build_combined_nav(nav_maps, weights, initial_nav=1.0):
    """
    合成组合净值。
    每日组合收益率 = Σ weight_i × ret_i
    """
    all_dates = set()
    for m in nav_maps.values():
        all_dates.update(m.keys())
    dates = sorted(all_dates)

    # 对齐: 只取所有策略都有数据的日期
    common_dates = [d for d in dates if all(d in m for m in nav_maps.values())]
    if not common_dates:
        return []

    first = min(common_dates)
    # 初始化时各策略净值
    initial_vals = {sid: nav_maps[sid][first] for sid in nav_maps}
    initial_portfolio = sum(weights[sid] for sid in weights)

    combined = []
    prev_vals = dict(initial_vals)
    prev_combined = initial_portfolio

    for i, d in enumerate(common_dates):
        if i == 0:
            # 首日: 归一化到 1.0
            combined.append({
                "date": d,
                "nav": initial_nav,
                "drawdown": 0.0,
            })
            continue

        # 计算各策略当日收益率
        daily_ret = 0.0
        for sid in weights:
            if d in nav_maps[sid] and prev_vals[sid] > 0:
                ret = nav_maps[sid][d] / prev_vals[sid] - 1
                daily_ret += weights[sid] * ret
                prev_vals[sid] = nav_maps[sid][d]

        prev_combined *= (1 + daily_ret)
        combined.append({
            "date": d,
            "nav": round(prev_combined, 6),
            "drawdown": 0.0,  # 后续计算
        })

    # 计算回撤
    peak = 0
    for p in combined:
        peak = max(peak, p["nav"])
        p["drawdown"] = round(p["nav"] / peak - 1, 4) if peak > 0 else 0

    return combined


def compute_folio_kpis(combined_nav):
    """从组合净值计算 KPI"""
    if len(combined_nav) < 2:
        return {}

    navs = np.array([p["nav"] for p in combined_nav])
    daily_ret = navs[1:] / navs[:-1] - 1
    n_days = len(daily_ret)

    ann_vol = float(np.std(daily_ret, ddof=1) * np.sqrt(252))
    sharpe = float(np.mean(daily_ret) / np.std(daily_ret, ddof=1) * np.sqrt(252)) if ann_vol > 0 else 0
    peak = np.maximum.accumulate(navs)
    dd = (navs - peak) / peak * 100
    mdd = float(np.min(dd))
    total_years = n_days / 252
    ann_ret = float(navs[-1] ** (1 / total_years) - 1) * 100 if total_years > 0 else 0
    tot_ret = float((navs[-1] - 1) * 100)

    return {
        "annual_return": round(ann_ret, 2),
        "total_return": round(tot_ret, 2),
        "sharpe": round(sharpe, 2),
        "max_drawdown": round(abs(mdd), 2),
        "annual_vol": round(ann_vol * 100, 2),
    }


if __name__ == "__main__":
    print("=" * 50)
    print("▶ 组合策略引擎 — 逆波动率加权")

    # 1. 加载数据
    nav_maps = {}
    nav_infos = {}
    for sdef in STRATEGIES:
        json_path = os.path.join(OUTPUT_DIR, sdef["json"])
        if not os.path.exists(json_path):
            print(f"  ❌ 文件不存在: {json_path}")
            continue
        nav_map, nav_list, sinfo = load_nav(json_path)
        nav_maps[sdef["id"]] = nav_map
        nav_infos[sdef["id"]] = sinfo
        print(f"  [{sdef['id']}] {len(nav_list)} 净值点, "
              f"{sinfo.get('start_date','?')}→{sinfo.get('end_date','?')}, "
              f"年化{sinfo.get('annual_return','?')}%")

    if len(nav_maps) < 2:
        print("  ❌ 策略不足2个，无法构建组合")
        exit(1)

    # 2. 计算权重
    weights = compute_inverse_vol_weights(nav_maps)

    # 3. 合成组合净值
    combined_nav = build_combined_nav(nav_maps, weights)
    print(f"  组合净值: {len(combined_nav)} 点, "
          f"{combined_nav[0]['date']}→{combined_nav[-1]['date']}")

    # 4. 计算 KPI
    kpis = compute_folio_kpis(combined_nav)
    print(f"  组合KPI: 年化{kpis['annual_return']}%  夏普{kpis['sharpe']}  回撤{kpis['max_drawdown']}%")

    # 5. 保存
    folio = {
        "id": "folio",
        "name": "综合组合(逆波动率加权)",
        "source": "多策略合成",
        "start_date": combined_nav[0]["date"],
        "end_date": combined_nav[-1]["date"],
        "weights": {sid: w for sid, w in weights.items()},
        "components": [
            {"id": s["id"], "name": s["name"], "weight": weights[s["id"]],
             "annual_return": nav_infos[s["id"]].get("annual_return", 0),
             "sharpe": nav_infos[s["id"]].get("sharpe", 0)}
            for s in STRATEGIES if s["id"] in weights
        ],
        **kpis,
        "rebalance": "daily",
        "nav_history": [{"date": p["date"], "nav": p["nav"], "is_simulation": False}
                        for p in combined_nav],
        "benchmark_nav": [1.0] * len(combined_nav),
        "position_snapshots": [],
        "trade_log": [],
        "monthly_trades": [],
    }

    json_path = os.path.join(OUTPUT_DIR, "folio.json")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"strategies": [folio]}, f, ensure_ascii=False, indent=2)
    print(f"  ✅ 保存: {json_path}")
    print(f"\n✅ 组合构建完成!")
