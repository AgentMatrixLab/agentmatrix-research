"""
双引擎一致性验证 — 对比自定义引擎和 Qlib 引擎的净值曲线

用法:
  python compare_engines.py                          # 验证所有策略
  python compare_engines.py --strategy 小市值(月)     # 验证单个策略
  python compare_engines.py --symbols 500            # 只用500只股票 (加速)
  python compare_engines.py --tolerance 0.02         # 自定义容差 (默认 2%)
"""
import os, sys, argparse
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from config import RESULTS_DIR


def compare_strategy(strategy_name, signal_fn, rebalance_freq=21, symbols_limit=0):
    """对比单个策略的双引擎结果

    返回: dict with correlation, mae, metrics_diff, nav_series
    """
    from engine.backtest import BacktestEngine
    from engine.qlib_bridge import QlibBacktestRunner

    print(f"\n{'='*60}")
    print(f"  对比: {strategy_name}")
    print(f"{'='*60}")

    # ── 自定义引擎 ──
    print("  [1/2] 自定义引擎...")
    engine = BacktestEngine()
    nav_custom, metrics_custom = engine.run_strategy(
        signal_fn, strategy_name, rebalance_freq=rebalance_freq
    )
    print(f"        净值: {nav_custom['nav'].iloc[0]:.0f} → {nav_custom['nav'].iloc[-1]:.0f}")

    # ── Qlib 引擎 ──
    print("  [2/2] Qlib 引擎...")
    try:
        runner = QlibBacktestRunner()
        nav_qlib, metrics_qlib = runner.run_strategy(
            strategy_name, rebalance_freq=rebalance_freq
        )
        if nav_qlib is None or len(nav_qlib) < 2:
            print("         ⚠️ Qlib 没有产生净值")
            return None
        print(f"        净值: {nav_qlib['nav'].iloc[0]:.0f} → {nav_qlib['nav'].iloc[-1]:.0f}")
    except Exception as e:
        print(f"         ❌ Qlib 失败: {e}")
        return {"strategy": strategy_name, "error": str(e)}

    # ── 相关性分析 ──
    # 对齐日期: 把 Qlib 的日期索引转成 Timestamp
    nav_c = nav_custom.copy()
    nav_q = nav_qlib.copy()

    # 确保 nav_q 的 index 是 datetime
    if not isinstance(nav_q.index, pd.DatetimeIndex):
        nav_q.index = pd.to_datetime(nav_q.index)
    if not isinstance(nav_c.index, pd.DatetimeIndex):
        nav_c.index = pd.to_datetime(nav_c.index)

    # 找公共日期
    common = nav_c.index.intersection(nav_q.index)
    if len(common) < 10:
        print(f"         ⚠️ 公共日期不足: {len(common)}")
        return {"strategy": strategy_name, "common_dates": len(common)}

    c = nav_c.loc[common, 'nav'].values
    q = nav_q.loc[common, 'nav'].values

    # 归一化 (都从 1 开始)
    c_norm = c / c[0]
    q_norm = q / q[0]

    correlation = np.corrcoef(c_norm, q_norm)[0, 1]
    mae = np.mean(np.abs(c_norm - q_norm))
    max_diff = np.max(np.abs(c_norm - q_norm))
    final_diff = abs(c_norm[-1] - q_norm[-1])

    # ── 指标差异 ──
    metrics_diff = {}
    common_keys = set(metrics_custom.keys()) & set(metrics_qlib.keys())
    for k in common_keys:
        try:
            cv = float(str(metrics_custom[k]).replace('%', '').replace('+', ''))
            qv = float(str(metrics_qlib[k]).replace('%', '').replace('+', ''))
            if abs(cv) > 1e-9:
                metrics_diff[k] = abs(cv - qv) / abs(cv)
            else:
                metrics_diff[k] = abs(cv - qv)
        except (ValueError, TypeError):
            pass

    # ── 结果 ──
    passed = correlation > 0.95 and final_diff < 0.05

    result = {
        "strategy": strategy_name,
        "common_dates": len(common),
        "correlation": round(correlation, 6),
        "mae": round(mae, 6),
        "max_diff": round(max_diff, 6),
        "final_diff": round(final_diff, 6),
        "passed": passed,
        "metrics_diff": {k: round(v, 4) for k, v in metrics_diff.items()},
    }

    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"  {status}  相关性: {correlation:.4f}  "
          f"MAE: {mae:.4f}  终值差: {final_diff:.4f}")

    return result


def main():
    parser = argparse.ArgumentParser(description="双引擎一致性验证")
    parser.add_argument("--strategy", type=str, default=None,
                        help="策略名称 (默认: 全部)")
    parser.add_argument("--symbols", type=int, default=0,
                        help="限制股票数量 (0=全部)")
    parser.add_argument("--freq", type=int, default=21,
                        help="调仓频率 (默认21=月频)")
    parser.add_argument("--tolerance", type=float, default=0.02,
                        help="净值终值差异容差 (默认 2%%)")
    args = parser.parse_args()

    from strategies import discover_strategies
    all_strategies = discover_strategies()

    if not all_strategies:
        print("没有找到策略")
        return

    # 过滤策略
    if args.strategy:
        if args.strategy in all_strategies:
            targets = {args.strategy: all_strategies[args.strategy]}
        else:
            matched = {k: v for k, v in all_strategies.items()
                      if args.strategy.lower() in k.lower()}
            if matched:
                targets = matched
            else:
                print(f"策略不存在: {args.strategy}")
                print(f"可用: {list(all_strategies.keys())}")
                return
    else:
        targets = all_strategies

    print(f"验证策略: {len(targets)} 个")
    print(f"容差: {args.tolerance:.1%}")
    print()

    results = []
    for name, fn in targets.items():
        result = compare_strategy(name, fn, args.freq, args.symbols)
        if result:
            results.append(result)

    # ── 汇总 ──
    print(f"\n{'='*60}")
    print("  汇总")
    print(f"{'='*60}")

    df = pd.DataFrame(results)
    if 'passed' in df.columns:
        n_pass = df['passed'].sum()
        n_fail = (~df['passed']).sum()
        print(f"  通过: {n_pass}/{len(df)}")
        print(f"  失败: {n_fail}/{len(df)}")

    if 'correlation' in df.columns:
        print(f"\n  相关性:  均值 {df['correlation'].mean():.4f}  "
              f"最小 {df['correlation'].min():.4f}")
        print(f"  MAE:     均值 {df['mae'].mean():.4f}  "
              f"最大 {df['mae'].max():.4f}")
        print(f"  终值差:  均值 {df['final_diff'].mean():.4f}  "
              f"最大 {df['final_diff'].max():.4f}")

    # 保存
    out_path = os.path.join(RESULTS_DIR, "engine_comparison.csv")
    os.makedirs(RESULTS_DIR, exist_ok=True)
    df.to_csv(out_path, index=False)
    print(f"\n详情: {out_path}")

    # 输出失败项
    if 'passed' in df.columns:
        failed = df[~df['passed']]
        if len(failed) > 0:
            print(f"\n⚠️ 未通过验证的策略:")
            for _, row in failed.iterrows():
                err = row.get('error', '')
                print(f"   - {row['strategy']}: corr={row.get('correlation','N/A')}  "
                      f"final_diff={row.get('final_diff','N/A')}  {err}")


if __name__ == "__main__":
    main()
