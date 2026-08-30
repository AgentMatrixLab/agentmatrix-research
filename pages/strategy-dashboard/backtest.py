"""简化回测引擎 — pages/strategy-dashboard

数据源：quant-api-v2（factor_monthly 33 因子 × 76 月末 + ods_kline_1d + ods_adj_factor_daily）
方法：月末调仓、等权 Top50 多头、含交易成本的净值曲线，与全A等权基准对比。
输出：data/backtest_results.json（供 generate_data.py 合并进 strategies.json）

运行：python3.11 pages/strategy-dashboard/backtest.py
缓存：runtime/strategy_dashboard_cache/（勿提交）

口径（简化版，面板注明）：
- 月末因子截面 → 横截面 zscore 合成得分 → Top50 等权持有 1 个月
- 收益 = 复权收盘价 t+1 / t − 1（t+1 无报价的持仓按剔除处理）
- 成本：买 0.13%（佣金+滑点）/ 卖 0.18%（佣金+印花税+滑点）
- 股票池：全A，剔除月均成交额 < 2000 万（可交易性过滤）；未剔除 ST/涨跌停（简化）
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "runtime/strategy_dashboard_cache"
OUT = Path(__file__).resolve().parent / "data/backtest_results.json"

# 凭证从环境变量读取（QUANT_API_BASE / QUANT_API_TOKEN），勿硬编码。
API_BASE = os.environ.get("QUANT_API_BASE", "http://115.159.73.134:8765")
API_TOKEN = os.environ.get("QUANT_API_TOKEN", "")
H = {"Authorization": f"Bearer {API_TOKEN}"}

# ── 回测参数 ──
TOP_N = 50                     # 持仓数
MIN_AMOUNT = 2e7               # 月均成交额下限（2000 万）
COST_BUY = 0.0003 + 0.001      # 佣金 + 滑点
COST_SELL = 0.0003 + 0.0005 + 0.001  # 佣金 + 印花税 + 滑点
BOOTSTRAP_N = 1000

# ═══════════════════ 策略定义 ═══════════════════
# factors: {factor_key: (direction, weight)}，direction=+1 做多大值，-1 做多小值
STRATEGY_DEFS = [
    # ── 原有 4 个（v1 已上线，保留 id；alpha1 无 factor_monthly 数据不回测） ──
    dict(strategy_id="quality_roe_top20_v1", factors={"roe_ttm": (1, 1)}),
    dict(strategy_id="trend_mom12_1_top30_v1", factors={"momentum_12_1": (1, 1)}),
    dict(strategy_id="low_vol_defensive_v1", factors={"volatility_1m": (-1, 1)}),
    dict(strategy_id="contrarian_reversal_v1", factors={"reversal": (1, 1)}),
    # ── 新增 19 个单因子 ──
    dict(strategy_id="mom_6m_top50_v1", factors={"ret_6m": (1, 1)}),
    dict(strategy_id="mom_voladj_3m_v1", factors={"ret_3m_vol_adj": (1, 1)}),
    dict(strategy_id="low_vol_3m_v1", factors={"volatility_3m": (-1, 1)}),
    dict(strategy_id="illiq_premium_v1", factors={"illiquidity": (1, 1)}),
    dict(strategy_id="low_turnover_v1", factors={"turnover_proxy": (-1, 1)}),
    dict(strategy_id="low_price_v1", factors={"log_price": (-1, 1)}),
    dict(strategy_id="rsi_reversal_v1", factors={"rsi_14": (-1, 1)}),
    dict(strategy_id="bb_reversal_v1", factors={"bb_position": (-1, 1)}),
    dict(strategy_id="anti_lottery_v1", factors={"max_ret_1m": (-1, 1)}),
    dict(strategy_id="low_amplitude_v1", factors={"amplitude_1m": (-1, 1)}),
    dict(strategy_id="ma_trend_v1", factors={"ma_signal": (1, 1)}),
    dict(strategy_id="quality_roa_v1", factors={"roa_ttm": (1, 1)}),
    dict(strategy_id="quality_margin_v1", factors={"net_margin": (1, 1)}),
    dict(strategy_id="growth_rev_v1", factors={"revenue_yoy": (1, 1)}),
    dict(strategy_id="growth_profit_v1", factors={"profit_yoy": (1, 1)}),
    dict(strategy_id="growth_eps_v1", factors={"eps_yoy": (1, 1)}),
    dict(strategy_id="quality_turnover_v1", factors={"asset_turnover": (1, 1)}),
    dict(strategy_id="low_leverage_v1", factors={"debt_to_asset": (-1, 1)}),
    dict(strategy_id="small_size_v1", factors={"log_amount_1m": (-1, 1)}),
    # ── 多因子组合（3 个） ──
    dict(strategy_id="multi_quality_growth_v1",
         factors={"roe_ttm": (1, 1.0), "net_margin": (1, 0.5),
                  "revenue_yoy": (1, 0.5), "debt_to_asset": (-1, 0.5)}),
    dict(strategy_id="multi_mom_lowvol_v1",
         factors={"momentum_12_1": (1, 1.0), "ret_3m_vol_adj": (1, 0.5),
                  "volatility_1m": (-1, 0.5)}),
    dict(strategy_id="multi_smart_beta_v1",
         factors={"roe_ttm": (1, 0.6), "momentum_12_1": (1, 0.4),
                  "revenue_yoy": (1, 0.4), "volatility_3m": (-1, 0.4),
                  "turnover_proxy": (-1, 0.3)}),
]


# ═══════════════════ 数据下载 ═══════════════════

def call(path, params=None, timeout=60):
    r = requests.get(f"{API_BASE}{path}", params=params, headers=H, timeout=timeout)
    r.raise_for_status()
    return r.json()


def fetch_factor_monthly() -> pd.DataFrame:
    """33 因子月频截面（缓存为 parquet）。"""
    f = CACHE / "factor_monthly.parquet"
    if not f.exists():
        r = requests.get(f"{API_BASE}/ch/factor_monthly/parquet", headers=H,
                         stream=True, timeout=600)
        r.raise_for_status()
        f.parent.mkdir(parents=True, exist_ok=True)
        with open(f, "wb") as fh:
            for chunk in r.iter_content(1024 * 1024):
                fh.write(chunk)
    df = pd.read_parquet(f)
    df["date"] = pd.to_datetime(df["trade_date"], unit="D", origin="unix")
    return df


def fetch_monthly_prices(dates: list[str]) -> pd.DataFrame:
    """因子月末日的收盘价 + 复权因子 → 复权收盘（缓存 parquet，增量补拉）。

    返回列：symbol, date_str, adj_close
    """
    f = CACHE / "monthly_prices.parquet"
    done: set[str] = set()
    parts: list[pd.DataFrame] = []
    if f.exists():
        old = pd.read_parquet(f)
        done = set(old["date_str"].unique())
        parts.append(old)
    todo = [d for d in dates if d not in done]
    if todo:
        new_rows = []
        for i, d in enumerate(todo):
            kl = call("/ch/ods_kline_1d", {"date": d, "factor": "symbol,close",
                                           "limit": 100000}).get("data", [])
            af = call("/ch/ods_adj_factor_daily", {"date": d, "factor": "symbol,adj_factor",
                                                   "limit": 100000}).get("data", [])
            adj = {r["symbol"]: r["adj_factor"] for r in af}
            for r in kl:
                a = adj.get(r["symbol"])
                if a is not None:
                    new_rows.append({"symbol": r["symbol"], "date_str": d,
                                     "adj_close": r["close"] * a})
            if (i + 1) % 10 == 0:
                print(f"  价格下载 {i + 1}/{len(todo)} 日期")
            time.sleep(0.1)
        if new_rows:
            parts.append(pd.DataFrame(new_rows))
        out = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(new_rows)
        f.parent.mkdir(parents=True, exist_ok=True)
        out.to_parquet(f, index=False)
        return out
    return parts[0]


# ═══════════════════ 回测核心 ═══════════════════

def zscore(s: pd.Series) -> pd.Series:
    sd = s.std(ddof=0)
    return (s - s.mean()) / sd if sd and sd > 0 else s * 0.0


def backtest_one(fdf: pd.DataFrame, pmap: dict, date_objs: list, sd: dict) -> dict:
    """单策略月频等权回测。pmap: {date_obj: {symbol: adj_close}}"""
    factors = sd["factors"]
    nav, rets, tos, n_holdings, ic_series = [1.0], [], [], [], []
    holdings_prev: dict[str, float] = {}
    prev_gross = 0.0

    for i in range(len(date_objs) - 1):
        t, t1 = date_objs[i], date_objs[i + 1]
        cross = fdf[fdf["date"] == t].set_index("symbol")
        pt, pt1 = pmap.get(t, {}), pmap.get(t1, {})

        # 可交易池：因子表内 + 两端有报价 + 成交额过滤
        tradable = cross["avg_amount_1m"].notna() & (cross["avg_amount_1m"] >= MIN_AMOUNT)
        pool = cross[tradable]
        pool = pool[pool.index.map(lambda s: s in pt and s in pt1)]

        # 合成得分（zscore × 方向 × 权重，缺失即 NaN）
        score = None
        for fk, (direc, w) in factors.items():
            z = zscore(pool[fk]) * direc * w
            score = z if score is None else score.add(z, fill_value=np.nan)
        valid = score.dropna()
        sel = valid.nlargest(TOP_N) if len(valid) > TOP_N else valid

        # 持仓收益（等权）
        rets_stocks = {s: pt1[s] / pt[s] - 1 for s in sel.index}
        gross = float(np.mean(list(rets_stocks.values()))) if rets_stocks else 0.0
        n_holdings.append(len(rets_stocks))

        # 换手率（上期权重漂移后 vs 新权重）
        if holdings_prev:
            w_drift = {s: w * (1 + rets_stocks.get(s, 0.0)) / (1 + prev_gross)
                       for s, w in holdings_prev.items()}
            w_new = {s: 1.0 / len(sel) for s in sel.index}
            one_way = sum(abs(w_new.get(s, 0.0) - w_drift.get(s, 0.0))
                          for s in set(w_drift) | set(w_new)) / 2
        else:
            one_way = 1.0  # 建仓
        tos.append(one_way)
        net = gross - one_way * (COST_BUY + COST_SELL)
        rets.append(net)
        nav.append(nav[-1] * (1 + net))
        holdings_prev = {s: 1.0 / len(sel) for s in sel.index}
        prev_gross = gross

        # 月度 Rank IC：合成得分 vs 下月收益（全池）
        if len(valid) > 30:
            fwd = pd.Series({s: pt1[s] / pt[s] - 1 for s in pool.index})
            common = valid.index.intersection(fwd.index)
            if len(common) > 30:
                ic_series.append(float(valid[common].rank().corr(fwd[common].rank())))

    return summarize(sd, date_objs, nav, rets, tos, n_holdings, ic_series)


def summarize(sd, date_objs, nav, rets, tos, n_holdings, ic_series) -> dict:
    n = len(rets)
    nav_arr = np.array(nav)
    ann_ret = nav_arr[-1] ** (12 / n) - 1 if n else None
    vol = float(np.std(rets, ddof=1) * np.sqrt(12)) if n > 1 else None
    sharpe = ann_ret / vol if (ann_ret is not None and vol and vol > 0) else None
    peak = np.maximum.accumulate(nav_arr)
    mdd = float(np.min(nav_arr / peak - 1)) if n else None

    ic = None
    if ic_series:
        arr = np.array(ic_series)
        mean, std = float(arr.mean()), float(arr.std(ddof=1))
        rng = np.random.default_rng(42)
        bs = [float(np.mean(rng.choice(arr, size=len(arr), replace=True)))
              for _ in range(BOOTSTRAP_N)]
        ic = {
            "mean_rank_ic": round(mean, 6),
            "ic_std": round(std, 6),
            "icir": round(mean / std, 4) if std > 0 else None,
            "t_stat": round(mean / std * np.sqrt(len(arr)), 3) if std > 0 else None,
            "ic_positive_ratio": round(float((arr > 0).mean()), 4),
            "bootstrap_ci95": [round(float(np.percentile(bs, 2.5)), 6),
                               round(float(np.percentile(bs, 97.5)), 6)],
            "n_months": len(arr),
        }
    ds = [d.strftime("%Y-%m-%d") for d in date_objs]
    return {
        "strategy_id": sd["strategy_id"],
        "nav": [[ds[i], round(float(nav[i]), 6)] for i in range(len(nav))],
        "metrics": {
            "annual_return": round(float(ann_ret), 4) if ann_ret is not None else None,
            "annual_vol": round(vol, 4) if vol else None,
            "sharpe": round(float(sharpe), 3) if sharpe is not None else None,
            "max_drawdown": round(mdd, 4) if mdd is not None else None,
            "avg_monthly_turnover": round(float(np.mean(tos)), 4) if tos else None,
            "avg_holdings": round(float(np.mean(n_holdings)), 1) if n_holdings else None,
            "n_months": n,
        },
        "ic": ic,
    }


def benchmark_equal_weight(fdf: pd.DataFrame, pmap: dict, date_objs: list) -> dict:
    """全A等权基准（同样含成交额过滤，不含成本）。"""
    rets = []
    for i in range(len(date_objs) - 1):
        t, t1 = date_objs[i], date_objs[i + 1]
        pt, pt1 = pmap.get(t, {}), pmap.get(t1, {})
        rs = [pt1[s] / pt[s] - 1 for s in pt if s in pt1]
        rets.append(float(np.mean(rs)) if rs else 0.0)
    return summarize(dict(strategy_id="__benchmark__"), date_objs,
                     list(np.cumprod([1.0] + [1 + r for r in rets])),
                     rets, [0.0] * len(rets), [], None)


# ═══════════════════ 主流程 ═══════════════════

def main():
    print("== 1/3 拉取因子数据 ==")
    fdf = fetch_factor_monthly()
    date_objs = sorted(fdf["date"].unique())
    dates = [d.strftime("%Y-%m-%d") for d in date_objs]
    print(f"  {fdf.shape[0]} 行 × {len(date_objs)} 个月末（{dates[0]} ~ {dates[-1]}）")

    print("== 2/3 拉取月末价格 + 复权因子 ==")
    price = fetch_monthly_prices(dates)
    print(f"  {len(price)} 条复权报价")
    pmap = {d: dict(g[["symbol", "adj_close"]].values)
            for d, g in price.assign(d=price["date_str"].map(
                lambda s: pd.Timestamp(s))).groupby("d")}

    print("== 3/3 回测 ==")
    bench = benchmark_equal_weight(fdf, pmap, date_objs)
    results = {}
    for sd in STRATEGY_DEFS:
        r = backtest_one(fdf, pmap, date_objs, sd)
        results[sd["strategy_id"]] = r
        m, ic = r["metrics"], r["ic"] or {}
        print(f"  {sd['strategy_id']:<30} 年化={m['annual_return']:+.1%} "
              f"夏普={m['sharpe']} 回撤={m['max_drawdown']:.1%} "
              f"IC={ic.get('mean_rank_ic', '—')}")

    doc = {
        "schema_version": "strategy_dashboard_backtest_v1",
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "method": "equal_weight_monthly_rebalance",
        "backtest_window": {"start": dates[0], "end": dates[-1], "n_months": len(dates) - 1},
        "cost_model": {"buy": COST_BUY, "sell": COST_SELL,
                       "note": "佣金0.03%+滑点0.1%（买）/ +印花税0.05%（卖）"},
        "universe_rule": f"全A，剔除月均成交额<{MIN_AMOUNT/1e7:.0f}千万；未剔除ST/涨跌停（简化口径）",
        "top_n": TOP_N,
        "benchmark": {"id": "equal_weight_all_a",
                      "nav": bench["nav"], "metrics": bench["metrics"]},
        "results": results,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    print(f"\nwritten: {OUT}")
    print(f"  基准（全A等权）年化={bench['metrics']['annual_return']:+.1%} "
          f"夏普={bench['metrics']['sharpe']} 回撤={bench['metrics']['max_drawdown']:.1%}")


if __name__ == "__main__":
    main()
