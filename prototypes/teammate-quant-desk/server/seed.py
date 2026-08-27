"""
种子数据生成 — 纯计算，无需外部数据文件
"""
import os, sys, json, random, math
import numpy as np

from config import INIT_CAPITAL

# 固定的策略定义
STRATEGY_DEFS = [
    {"id": "alpha",        "name": "阿尔法混合多策略",  "tag": "多策略", "version": "v2.4.1", "status": "running"},
    {"id": "momentum",     "name": "动量轮动增强",      "tag": "趋势",   "version": "v3.1",   "status": "running"},
    {"id": "cta",          "name": "CTA 趋势跟踪",       "tag": "CTA",    "version": "v1.5",   "status": "paused"},
    {"id": "arb",          "name": "中性套利一号",       "tag": "套利",   "version": "v2.0",   "status": "running"},
    {"id": "div_v5",       "name": "红利策略v5",        "tag": "红利",   "version": "v5.2",   "status": "running"},
    {"id": "barra_4f",     "name": "Barra四因子",       "tag": "多因子", "version": "v1.3",   "status": "running"},
    {"id": "reversal",     "name": "5日反转",           "tag": "反转",   "version": "v1.2",   "status": "running"},
]

STOCK_POOL = [
    ("600519", "贵州茅台"), ("000858", "五粮液"), ("601318", "中国平安"),
    ("000333", "美的集团"), ("002415", "海康威视"), ("600276", "恒瑞医药"),
    ("601888", "中国中免"), ("002594", "比亚迪"), ("300750", "宁德时代"),
    ("000725", "京东方A"), ("600887", "伊利股份"), ("601166", "兴业银行"),
    ("600036", "招商银行"), ("000651", "格力电器"), ("002475", "立讯精密"),
    ("600900", "长江电力"), ("000568", "泸州老窖"), ("603259", "药明康德"),
    ("002714", "牧原股份"), ("601012", "隆基绿能"), ("300059", "东方财富"),
    ("601398", "工商银行"), ("600030", "中信证券"), ("002230", "科大讯飞"),
    ("000002", "万科A"), ("600585", "海螺水泥"), ("300124", "汇川技术"),
    ("601688", "华泰证券"), ("002142", "宁波银行"), ("603288", "海天味业"),
]

# 固定种子保证可复现
SEED_MAPS = {
    "alpha": 42, "momentum": 520, "cta": 7, "arb": 999,
    "div_v5": 314, "barra_4f": 2718, "reversal": 88,
}


def _generate_nav_series(strategy_id: str) -> list:
    """用几何布朗运动 + 真实日内波动生成净值序列"""
    rng = np.random.RandomState(SEED_MAPS.get(strategy_id, 42))
    n_days = 750  # ~3 years
    annual_ret = rng.uniform(0.05, 0.55)
    annual_vol = rng.uniform(0.08, 0.22)
    daily_ret_mean = annual_ret / 252
    daily_vol = annual_vol / np.sqrt(252)

    nav = 1.0
    peak = 1.0
    base_date = np.datetime64("2023-08-01")
    nav_series = []

    # 生成有放假间隔的日期序列
    business_days = []
    d = base_date
    while len(business_days) < n_days:
        wd = d.astype(object).weekday()
        if wd < 5:  # Mon-Fri
            business_days.append(d)
        d += np.timedelta64(1, "D")

    for date in business_days:
        ret = rng.normal(daily_ret_mean, daily_vol)
        nav *= (1 + ret)
        peak = max(peak, nav)
        dd = nav / peak - 1 if peak > 0 else 0
        nav_series.append({
            "date": str(date)[:10],
            "nav": round(float(nav), 4),
            "benchmark": round(float(min(nav * (1 + rng.normal(0, 0.003)), peak * 1.1)), 4),
            "drawdown": round(float(dd), 4),
        })
    return nav_series


def _calc_kpis(nav_series):
    if len(nav_series) < 2:
        return {}
    navs = np.array([p["nav"] for p in nav_series])
    total_ret = navs[-1] / navs[0] - 1
    n_years = len(navs) / 252
    ann_ret = (1 + total_ret) ** (1 / max(n_years, 0.5)) - 1
    daily_rets = np.diff(navs) / navs[:-1]
    ann_vol = float(np.std(daily_rets, ddof=1) * math.sqrt(252))
    sharpe = float(np.mean(daily_rets) / np.std(daily_rets, ddof=1) * math.sqrt(252)) if np.std(daily_rets, ddof=1) > 0 else 0
    mdd = float(np.min(navs / np.maximum.accumulate(navs) - 1))
    wr = float(np.mean(daily_rets > 0))
    return {
        "total_return": round(total_ret, 4),
        "annual_return": round(ann_ret, 4),
        "sharpe": round(sharpe, 3),
        "max_drawdown": round(mdd, 4),
        "win_rate": round(wr, 3),
        "volatility": round(ann_vol, 4),
    }


def _generate_holdings(strategy_id):
    rng = random.Random(SEED_MAPS.get(strategy_id, 42))
    n_hold = rng.randint(6, 12)
    selected = rng.sample(STOCK_POOL, min(n_hold, len(STOCK_POOL)))
    holdings = []
    for code, name in selected:
        price = round(rng.uniform(8, 2500), 2)
        qty = rng.randint(100, 5000) // 100 * 100
        cost = round(price * rng.uniform(0.8, 1.05), 2)
        value = round(qty * price, 2)
        pnl = round(qty * (price - cost), 2)
        pnl_pct = round((price - cost) / cost, 4) if cost > 0 else 0
        industries = ["食品饮料", "金融", "科技", "医药", "新能源", "消费", "制造"]
        holdings.append({
            "code": code, "name": name,
            "industry": rng.choice(industries),
            "qty": qty, "cost": cost, "price": price, "value": value,
            "pnl": pnl, "pnl_pct": pnl_pct,
        })
    total_val = sum(h["value"] for h in holdings)
    if total_val > 0:
        for h in holdings:
            h["weight"] = round(h["value"] / total_val, 4)
    return sorted(holdings, key=lambda x: x["value"], reverse=True)


def _generate_trades(strategy_id, n=35):
    rng = random.Random(SEED_MAPS.get(strategy_id, 42) + 1000)
    base_date = np.datetime64("2025-08-01")
    trades = []
    for i in range(n):
        code, name = rng.choice(STOCK_POOL)
        day_offset = rng.randint(0, 500)
        d = base_date + np.timedelta64(day_offset, "D")
        while d.astype(object).weekday() >= 5:
            d += np.timedelta64(1, "D")
        price = round(rng.uniform(8, 2500), 2)
        side = rng.choice(["buy", "sell"])
        qty = rng.randint(1, 50) * 100
        amount = round(price * qty, 2)
        fee = round(amount * 0.0003 + 5, 2) if side == "buy" else round(amount * 0.0013 + 5, 2)
        trades.append({
            "time": f"{str(d)[:10]} {rng.randint(9,15):02d}:{rng.randint(0,59):02d}:{rng.randint(0,59):02d}",
            "code": code, "name": name,
            "side": side, "price": price, "qty": qty,
            "amount": amount, "fee": fee,
        })
    return sorted(trades, key=lambda x: x["time"], reverse=True)


def _sub_strategies(strategy_id):
    if strategy_id == "alpha":
        return [
            {"name": "动量轮动", "weight": 0.32, "contribution": 0.286},
            {"name": "低波防御", "weight": 0.25, "contribution": 0.112},
            {"name": "质量精选", "weight": 0.20, "contribution": 0.145},
            {"name": "事件驱动", "weight": 0.15, "contribution": 0.057},
            {"name": "择时对冲", "weight": 0.08, "contribution": 0.040},
        ]
    return []


def run_seed(db):
    print("[Seed] 生成种子数据（纯计算，无需 Parquet）...")

    for sdef in STRATEGY_DEFS:
        sid = sdef["id"]
        print(f"  [{sid}] {sdef['name']}...")

        db.execute(
            "INSERT OR REPLACE INTO strategies (id, name, tag, status, version) VALUES (?,?,?,?,?)",
            [sid, sdef["name"], sdef["tag"], sdef["status"], sdef["version"]]
        )

        # 净值
        nav = _generate_nav_series(sid)
        db.executemany(
            "INSERT OR REPLACE INTO nav_series (strategy_id, date, nav, benchmark_nav, drawdown) VALUES (?,?,?,?,?)",
            [(sid, p["date"], p["nav"], p["benchmark"], p["drawdown"]) for p in nav]
        )

        # KPI
        kpis = _calc_kpis(nav)
        db.execute(
            """INSERT OR REPLACE INTO kpis (strategy_id, total_return, annual_return, sharpe, max_drawdown, win_rate, volatility)
               VALUES (?,?,?,?,?,?,?)""",
            [sid, kpis["total_return"], kpis["annual_return"], kpis["sharpe"],
             kpis["max_drawdown"], kpis["win_rate"], kpis["volatility"]]
        )

        # 持仓
        holdings = _generate_holdings(sid)
        db.executemany(
            """INSERT INTO holdings (strategy_id, code, name, industry, qty, cost, price, value, pnl, pnl_pct, weight)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            [(sid, h["code"], h["name"], h["industry"], h["qty"], h["cost"],
              h["price"], h["value"], h["pnl"], h["pnl_pct"], h["weight"])
             for h in holdings]
        )

        # 成交
        trades = _generate_trades(sid)
        db.executemany(
            """INSERT INTO trades (strategy_id, time, code, name, side, price, qty, amount, fee)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            [(sid, t["time"], t["code"], t["name"], t["side"],
              t["price"], t["qty"], t["amount"], t["fee"]) for t in trades]
        )

    # 预警
    alerts = [
        ("dd", "alpha", "最大回撤超限", "≤ -15%", "-11.4%", 0, 1),
        ("var", "alpha", "VaR 超限", "≤ -2%", "-1.82%", 0, 1),
        ("vol", "alpha", "波动率超限", "≤ 25%", "17.6%", 0, 1),
        ("lev", "alpha", "杠杆率超限", "≤ 1.2x", "1.0x", 0, 0),
        ("conc", "alpha", "单一持仓超限", "≤ 20%", "15.3%", 0, 1),
    ]
    db.executemany(
        "INSERT OR REPLACE INTO alerts (id, strategy_id, rule, threshold, current_val, triggered, enabled) VALUES (?,?,?,?,?,?,?)",
        alerts
    )

    db.commit()
    print("[Seed] 完成")
