"""
阶段1: 生成信号 → 保存到文件

与Qlib完全解耦，不import qlib，内存安全。
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(__file__))
import pandas as pd
import numpy as np

OUT = os.path.join(os.path.dirname(__file__), "data", "signals_dividend_v6.parquet")

def generate_signals():
    print("[1] 加载K线...", end=' ', flush=True)
    t0 = time.time()
    kline = pd.read_parquet(os.path.join("data", "kline_adj.parquet"))
    kline['trade_date'] = pd.to_datetime(kline['trade_date'])
    # 只保留2017+减少内存
    kline = kline[kline['trade_date'] >= '2017-01-01']
    print(f"{len(kline):,}行, {kline['symbol'].nunique()}股票, {time.time()-t0:.1f}s")

    print("[2] 确定调仓日(半年度)...", end=' ', flush=True)
    all_dates = sorted(kline['trade_date'].unique())
    start = pd.Timestamp('2017-01-03')
    end = pd.Timestamp('2026-04-09')
    trade_dates = [d for d in all_dates if start <= d <= end]
    rebalance_dates = []
    last_ym = None
    for d in trade_dates:
        ym = (d.year, (d.month - 1) // 6 + 1)
        if ym != last_ym:
            rebalance_dates.append(pd.Timestamp(d))
            last_ym = ym
    print(f"{len(rebalance_dates)}个")

    print("[3] 生成信号...")
    from strategies.dividend_yield_v6 import get_signals
    signal_rows = []
    for i, d in enumerate(rebalance_dates):
        today = kline[kline['trade_date'] == d]
        if len(today) == 0:
            continue
        try:
            signals = get_signals(today)
        except Exception as e:
            print(f"  {d.date()} 出错: {e}")
            continue
        if signals is None or len(signals) == 0 or 'weight' not in signals.columns:
            print(f"  {d.date()}: 0只入选")
            continue
        total_w = signals['weight'].sum()
        n_sig = 0
        for _, row in signals.iterrows():
            signal_rows.append({
                'datetime': d,
                'instrument': str(row['symbol']),
                'score': float(row['weight']) / total_w if total_w > 0 else 0,
            })
            n_sig += 1
        print(f"  {d.date()}: {n_sig}只入选")

    print(f"  总信号: {len(signal_rows)}条")

    if not signal_rows:
        print("ERROR: 无信号!")
        return None

    df = pd.DataFrame(signal_rows)
    # 检查symbol格式是否对齐Qlib (.SZ/.SH vs .XSHE/.XSHG)
    sample = df['instrument'].iloc[0]
    print(f"  signal symbol格式: {sample}")

    df.to_parquet(OUT, index=False)
    print(f"  已保存: {OUT} ({os.path.getsize(OUT)/1024:.1f}KB)")
    return df

if __name__ == "__main__":
    print("=" * 55)
    print("阶段1: 信号生成 (红利v6)")
    print("=" * 55)
    generate_signals()
    print("=== 完成 ===")
