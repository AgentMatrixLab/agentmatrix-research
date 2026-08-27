"""
微盘股策略 — Backtrader 版
使用 bt_shared.py 统一引擎, A股真实成本
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime
import pandas as pd
from bt_shared import run_backtrader, compute_metrics, DATA_DIR, INITIAL_CASH
from strategies.micro_cap import get_signals as micro_cap_fn

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")


def get_rebalance_dates(kline, freq=21):
    """每月调仓"""
    all_dates = sorted(kline['trade_date'].unique())
    start_idx = freq
    rebalance_dates = []
    for i in range(start_idx, len(all_dates), freq):
        rebalance_dates.append(all_dates[i])
    return rebalance_dates


def precompute_signal_map(kline, strategy_fn, rebalance_dates):
    signal_map = {}
    sorted_dates = []
    for d in rebalance_dates:
        day_data = kline[kline['trade_date'] == d]
        if len(day_data) == 0:
            continue
        tradable_df = day_data[['symbol', 'trade_date']].copy()
        result = strategy_fn(tradable_df)
        if result is not None and len(result) > 0:
            weights = dict(zip(result['symbol'], result['weight']))
            date_str = d.strftime('%Y-%m-%d') if hasattr(d, 'strftime') else str(d)[:10]
            signal_map[date_str] = weights
            sorted_dates.append(date_str)
    return signal_map, sorted_dates


if __name__ == "__main__":
    print(f"=" * 50)
    print(f"▶ 微盘股策略 (Backtrader, 每21天/月度调仓)")

    kline = pd.read_parquet(f"{DATA_DIR}/kline_adj.parquet")
    if kline['trade_date'].dtype.name == 'uint16':
        kline['trade_date'] = pd.to_datetime(kline['trade_date'], unit='D', origin='unix')
    print(f"  K线: {kline['trade_date'].min().date()}→{kline['trade_date'].max().date()}")

    rb_dates = get_rebalance_dates(kline, 21)
    signal_map, sorted_dates = precompute_signal_map(kline, micro_cap_fn, rb_dates)
    
    all_syms = set()
    for w in signal_map.values():
        all_syms.update(w.keys())
    print(f"  信号日: {len(sorted_dates)} 次调仓, 涉及 {len(all_syms)} 只股票")

    if not signal_map:
        print("❌ 无有效信号")
        exit(1)

    # 限制数据馈送数（微盘股每期400只，总量可能很大）
    if len(all_syms) > 800:
        limited_map = {}
        for d, weights in signal_map.items():
            top = sorted(weights.items(), key=lambda x: x[1], reverse=True)[:800]
            limited_map[d] = dict(top)
        signal_map = limited_map
        all_syms2 = set()
        for w in signal_map.values():
            all_syms2.update(w.keys())
        print(f"  限制 Top 800 后: {len(all_syms2)} 只")

    dates, navs, trade_log, pos_snapshots = run_backtrader(signal_map, sorted_dates, signal_start=sorted_dates[0],
                                 preloaded_kline=kline)
    
    if not navs:
        print("❌ 未获取净值")
        exit(1)

    metrics = compute_metrics(dates, navs)
    final = navs[-1]
    ret = (final / INITIAL_CASH - 1) * 100
    print(f"  ✅ 终值: {final:,.0f}  收益: {ret:+.2f}%  年化: {metrics['annual_return']:.2f}%  "
          f"夏普: {metrics['sharpe']:.2f}  回撤: {metrics['max_drawdown']:.2f}%")

    nav_history = [{"date": d, "nav": round(v, 2), "is_simulation": False} 
                   for d, v in zip(dates, navs)]

    strategy = {
        "id": "micro_cap_400",
        "name": "微盘股(最小400)",
        "source": "Backtrader A股引擎",
        "start_date": nav_history[0]['date'],
        "end_date": nav_history[-1]['date'],
        **metrics,
        "rebalance": "21d",
        "nav_history": nav_history,
        "benchmark_nav": [1.0] * len(nav_history),
        "position_snapshots": pos_snapshots,
        "trade_log": trade_log,
        "monthly_trades": [],
    }

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    json_path = os.path.join(OUTPUT_DIR, "micro_cap_400.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"strategies": [strategy], "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S")},
                  f, ensure_ascii=False, indent=2)
    print(f"  ✅ 保存: {json_path}")
    print(f"\n✅ 全部完成!")
