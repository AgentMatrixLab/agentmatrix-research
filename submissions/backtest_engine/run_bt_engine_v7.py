"""
用已验证的 backtest.py 引擎 + 本地精简K线

与 dividend_v6_2017_2026_nav.csv (+130.24%) 一致的回测逻辑，
但使用精简数据（仅信号涉及的股票列）。
"""
import os, sys, time, gc, warnings
warnings.filterwarnings('ignore')

sys.path.insert(0, os.path.dirname(__file__))

def _setup_env():
    for k in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:
        os.environ.setdefault(k, '1')
_setup_env()

if __name__ == "__main__":
    import pandas as pd
    import numpy as np

    BASE = os.path.dirname(os.path.abspath(__file__))
    from config import DATA_DIR, INIT_CAPITAL, BACKTEST_YEARS

    print("=" * 55)
    print("回测: 红利v6 (backtest.py引擎 + 精简K线)")
    print("=" * 55)

    # === 1. 读信号 ===
    print("[1] 读取信号...", end=' ', flush=True)
    sig_df = pd.read_parquet(os.path.join(BASE, "data", "signals_dividend_v6.parquet"))
    # .SZ/.SH → .XSHE/.XSHG (对齐kline)
    sig_df['symbol'] = sig_df['instrument'].str.replace('.SZ', '.XSHE', regex=False).str.replace('.SH', '.XSHG', regex=False)
    signal_syms = set(sig_df['symbol'].unique())
    print(f"{len(signal_syms)}只信号股票")

    # === 2. 加载精简K线 ===
    print("[2] 加载K线...", end=' ', flush=True)
    t0 = time.time()
    kline = pd.read_parquet(os.path.join(BASE, "data", "kline_adj_lean.parquet"))
    kline['trade_date'] = pd.to_datetime(kline['trade_date'])
    # 只保留信号股票
    kline = kline[kline['symbol'].isin(signal_syms)]
    print(f"{len(kline):,}行, {time.time()-t0:.1f}s")

    # === 3. 加载完整K线（仅用于日历） ===
    # backtest.py的run_strategy需要完整日历
    # 我们直接从精简K线提取
    full_kline_path = os.path.join(BASE, "data", "kline_adj.parquet")
    if os.path.exists(full_kline_path):
        # 只读日期列
        print("[3] 提取日历...", end=' ', flush=True)
        cal_df = pd.read_parquet(full_kline_path, columns=['trade_date'])
        cal_df['trade_date'] = pd.to_datetime(cal_df['trade_date'])
        calendar = pd.DataFrame({'trade_date': sorted(cal_df['trade_date'].unique())})
    else:
        calendar = pd.DataFrame({'trade_date': sorted(kline['trade_date'].unique())})
    print(f"{len(calendar)}天")

    # 释放
    del cal_df
    gc.collect()

    # === 4. 使用 backtest.py 引擎 ===
    print("[4] 初始化引擎...")
    from engine.backtest import BacktestEngine

    class LeanBacktestEngine(BacktestEngine):
        """精简版回测引擎：只加载信号股票数据，大幅减少内存"""
        
        def __init__(self):
            self.data_dir = DATA_DIR
            # 不调用 super().__init__() 避免加载全部数据
            self.kline = kline
            self.calendar = calendar
            self.status = None
            self._valid_symbols = None
            self.financial = None
            self.financial_path = None
            
            print(f"  K线: {len(self.kline)}行, {self.kline['symbol'].nunique()}股票")
            print(f"  日历: {len(self.calendar)}天")

        def _load_data(self):
            pass  # 跳过自动加载

        def _filter_tradable(self, today):
            """简化版可交易过滤（无ST/停牌/退市数据，只过滤无效价格）"""
            if len(today) == 0:
                return today
            today = today.copy()
            today = today[today['close_adj'] > 0]
            return today

        def _calc_basic_factors(self, df):
            """只需ret_1d"""
            df = df.sort_values(['symbol', 'trade_date'])
            df['ret_1d'] = df.groupby('symbol')['close_adj'].pct_change()
            return df

    # lambda包装策略（适配 get_signals 接口）
    from strategies.dividend_yield_v6 import get_signals
    
    def signal_fn(df):
        return get_signals(df)

    engine = LeanBacktestEngine()

    print("[5] 运行回测 (2020-01-02 ~ 2026-04-09)...")
    t0 = time.time()

    try:
        nav_df, trades, metrics = engine.run_strategy(
            signal_fn, 
            name="红利v6",
            rebalance_freq=1,  # 每个调仓日
            start_date='2020-01-02',
            end_date='2026-04-09',
        )
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    elapsed = time.time() - t0
    print(f"\n  回测耗时: {elapsed:.1f}s")

    # === 5. 结果 ===
    print("\n" + "=" * 55)
    print("回测结果: 红利v6 (backtest.py引擎)")
    print("=" * 55)
    
    if isinstance(metrics, dict):
        mk_map = {
            'total_return': '总收益率',
            'annual_return': '年化收益',
            'annual_volatility': '年化波动',
            'max_drawdown': '最大回撤',
            'sharpe_ratio': '夏普比率',
            'win_rate': '胜率',
        }
        for k, v in metrics.items():
            label = mk_map.get(k, k)
            if isinstance(v, str) and '%' in v:
                print(f"  {label}: {v}")
            elif isinstance(v, (int, float)):
                if 'return' in k.lower() or 'drawdown' in k.lower() or 'win' in k.lower() or 'volat' in k.lower():
                    print(f"  {label}: {v:.2%}")
                elif 'ratio' in k.lower() or 'sharpe' in k.lower():
                    print(f"  {label}: {v:.2f}")
                else:
                    print(f"  {label}: {v:.4f}")
            else:
                print(f"  {label}: {v}")

    if nav_df is not None and len(nav_df) > 1:
        sv = nav_df['nav'].iloc[0]
        ev = nav_df['nav'].iloc[-1]
        print(f"\n  净值: {sv:,.0f} -> {ev:,.0f}  ({(ev/sv-1)*100:+.1f}%)")
        print(f"  交易日: {len(nav_df)}")

        out_dir = os.path.join(BASE, "results")
        os.makedirs(out_dir, exist_ok=True)
        nav_out = os.path.join(out_dir, "dividend_v6_engine_nav.csv")
        nav_df.reset_index().to_csv(nav_out, index=False)
        print(f"  保存: {nav_out}")

    print("=== 完成 ===")
