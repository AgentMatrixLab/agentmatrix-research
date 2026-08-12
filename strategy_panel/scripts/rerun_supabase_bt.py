"""
Supabase 信号策略 — Backtrader 回测
使用 fetch_supabase_signals.py 生成的信号文件

信号来源: Supabase signals 表 (daily_stock_pool + monthly_etf_pool, 剔除ETF)
调仓: 仅在信号日调仓，按 target_position 分配权重
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime
import pandas as pd
from bt_shared import run_backtrader, compute_metrics, DATA_DIR, INITIAL_CASH

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")
SIGNAL_FILE = os.path.join(OUTPUT_DIR, "supabase_signals.json")


def load_signal_map():
    """从 JSON 加载信号映射: {date_str: {symbol: weight}}"""
    with open(SIGNAL_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    signal_map = {}
    for date_str, sigs in data.get("signals", {}).items():
        weights = {}
        for s in sigs:
            if s["action"] in ("HOLD", "BUY"):
                w = s["weight"]
                if w > 0:
                    weights[s["symbol"]] = w
        if weights:
            signal_map[date_str] = weights
    
    sorted_dates = sorted(signal_map.keys())
    return signal_map, sorted_dates


if __name__ == "__main__":
    print("=" * 50)
    print("Supabase 信号策略  Backtrader")

    if not os.path.exists(SIGNAL_FILE):
        print("  Run fetch_supabase_signals.py first")
        exit(1)

    signal_map, sorted_dates = load_signal_map()
    print(f"  信号日: {len(sorted_dates)} 天, {sorted_dates[0]} -> {sorted_dates[-1]}")

    all_syms = set()
    for w in signal_map.values():
        all_syms.update(w.keys())
    print(f"  涉及股票: {len(all_syms)} 只")

    if not signal_map:
        print("  No valid signals")
        exit(1)

    # 加载 K 线
    kline = pd.read_parquet(f"{DATA_DIR}/kline_adj.parquet")
    if kline['trade_date'].dtype.name == 'uint16':
        kline['trade_date'] = pd.to_datetime(kline['trade_date'], unit='D', origin='unix')
    print(f"  K线: {kline['trade_date'].min().date()} -> {kline['trade_date'].max().date()}")

    # 过滤股票: 只保留 K 线中存在的
    kline_syms = set(kline['symbol'].unique())
    missing = all_syms - kline_syms
    if missing:
        print(f"  K线缺失: {len(missing)} 只")
    valid = all_syms & kline_syms
    print(f"  有效股票: {len(valid)} 只")
    
    # 过滤 signal_map
    filtered_map = {}
    for d, wmap in signal_map.items():
        fw = {s: w for s, w in wmap.items() if s in valid}
        if fw:
            filtered_map[d] = fw
    filtered_dates = [d for d in sorted_dates if d in filtered_map]
    print(f"  有效信号日: {len(filtered_dates)} 天")

    # 回测
    dates, navs, trade_log, pos_snapshots = run_backtrader(
        filtered_map, filtered_dates,
        signal_start=filtered_dates[0],
        preloaded_kline=kline,
    )

    if not navs:
        print("  No NAV generated")
        exit(1)

    metrics = compute_metrics(dates, navs)
    final = navs[-1]
    ret = (final / INITIAL_CASH - 1) * 100
    print(f"  Final: {final:,.0f}  Return: {ret:+.2f}%  Annual: {metrics['annual_return']:.2f}%  "
          f"Sharpe: {metrics['sharpe']:.2f}  DD: {metrics['max_drawdown']:.2f}%")

    nav_history = [{"date": d, "nav": round(v, 2), "is_simulation": False}
                   for d, v in zip(dates, navs)]

    strategy = {
        "id": "supabase_signals",
        "name": "Supabase信号策略",
        "source": "Supabase signals (image_signal)",
        "start_date": nav_history[0]['date'],
        "end_date": nav_history[-1]['date'],
        **metrics,
        "rebalance": "signal_driven",
        "nav_history": nav_history,
        "benchmark_nav": [1.0] * len(nav_history),
        "position_snapshots": pos_snapshots,
        "trade_log": trade_log,
        "monthly_trades": [],
    }

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    json_path = os.path.join(OUTPUT_DIR, "supabase_strategy.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"strategies": [strategy], "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S")},
                  f, ensure_ascii=False, indent=2)
    print(f"  Saved: {json_path}")
    print()
    print("All done!")
