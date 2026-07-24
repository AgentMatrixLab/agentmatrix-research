"""
🚀 运行所有策略回测

用法:
  python run_all.py                        # 全量回测 (自定义引擎)
  python run_all.py --engine qlib          # 全量回测 (Qlib引擎)
  python run_all.py --engine both          # 双引擎对比
  python run_all.py --freq 10              # 每10天调仓 (默认5)
  python run_all.py --strategy small_cap   # 只跑特定策略 (需用策略key)
"""
import os, sys, argparse, json
from datetime import datetime
sys.path.insert(0, os.path.dirname(__file__))

from config import STRATEGY_DIR, RESULTS_DIR, INIT_CAPITAL, BACKTEST_YEARS
from engine.backtest import BacktestEngine
from engine.metrics import format_report


def run_custom(strategies, rebalance_freq):
    """用自定义引擎跑"""
    engine = BacktestEngine()
    all_nav, all_metrics, report = engine.run_all(strategies, rebalance_freq)
    return all_nav, all_metrics, report


def run_qlib(strategies, rebalance_freq):
    """用 Qlib 引擎跑"""
    from engine.qlib_bridge import QlibBacktestRunner

    runner = QlibBacktestRunner()
    all_nav = {}
    all_metrics = {}

    for name in strategies:
        print(f"\n  ▶ {name} (Qlib)")
        try:
            nav_df, metrics = runner.run_strategy(
                name, rebalance_freq=rebalance_freq
            )
            all_nav[name] = nav_df
            all_metrics[name] = metrics
        except Exception as e:
            print(f"  ❌ {name} Qlib回测失败: {e}")
            all_metrics[name] = {"错误": str(e)}

    report = format_report(all_metrics)
    print("\n" + report)
    return all_nav, all_metrics, report


def run_both(strategies, rebalance_freq):
    """双引擎都跑, 输出对比"""
    print("\n" + "=" * 60)
    print("  自定义引擎")
    print("=" * 60)
    custom_nav, custom_metrics, custom_report = run_custom(strategies, rebalance_freq)

    print("\n" + "=" * 60)
    print("  Qlib 引擎")
    print("=" * 60)
    qlib_nav, qlib_metrics, qlib_report = run_qlib(strategies, rebalance_freq)

    # 合并对比
    merged_metrics = {}
    for name in strategies:
        c = custom_metrics.get(name, {})
        q = qlib_metrics.get(name, {})
        merged = {}
        all_keys = set(c.keys()) | set(q.keys())
        for k in all_keys:
            cv = c.get(k, "-")
            qv = q.get(k, "-")
            merged[k] = f"{cv} / {qv}" if cv != qv else cv
        merged_metrics[name] = merged

    report = format_report(merged_metrics)
    print("\n" + "=" * 60)
    print("  对比 (自定义 / Qlib)")
    print("=" * 60)
    print(report)

    return custom_nav, custom_metrics, custom_report


def main():
    parser = argparse.ArgumentParser(description="批量回测")
    parser.add_argument("--freq", type=int, default=5,
                        help="调仓频率 (交易日数, 默认5=周频)")
    parser.add_argument("--engine", type=str, default="custom",
                        choices=["custom", "qlib", "both"],
                        help="回测引擎: custom(自定义) / qlib(Qlib) / both(双引擎对比)")
    parser.add_argument("--strategy", type=str, default=None,
                        help="只跑特定策略 (用策略内部 key, 如 small_cap)")
    args = parser.parse_args()

    # 发现策略
    from strategies import discover_strategies
    strategies = discover_strategies()

    if not strategies:
        print("\n⚠️  没有找到策略文件!")
        print(f"   请在 {STRATEGY_DIR} 下创建策略文件")
        return

    # 如果指定了单个策略, 过滤
    if args.strategy:
        if args.strategy in strategies:
            strategies = {args.strategy: strategies[args.strategy]}
        else:
            # 尝试模糊匹配
            matched = {k: v for k, v in strategies.items()
                      if args.strategy.lower() in k.lower()}
            if matched:
                strategies = matched
            else:
                print(f"策略 '{args.strategy}' 不存在")
                print(f"可用: {list(strategies.keys())}")
                return

    print("=" * 60)
    print(f"🚀 批量回测")
    print(f"   引擎: {args.engine}")
    print(f"   策略数: {len(strategies)}")
    print(f"   回测窗口: {BACKTEST_YEARS}年")
    print(f"   初始资金: {INIT_CAPITAL:,.0f}")
    print(f"   调仓频率: 每{args.freq}天")
    print("=" * 60)

    print(f"\n策略列表:")
    for name in strategies:
        print(f"  - {name}")

    # 执行
    if args.engine == "custom":
        all_nav, all_metrics, report = run_custom(strategies, args.freq)
    elif args.engine == "qlib":
        all_nav, all_metrics, report = run_qlib(strategies, args.freq)
    else:  # both
        all_nav, all_metrics, report = run_both(strategies, args.freq)

    # 保存结果
    today_str = datetime.now().strftime("%Y-%m-%d")
    engine_tag = args.engine
    result_dir = os.path.join(RESULTS_DIR, f"{today_str}_{engine_tag}")
    os.makedirs(result_dir, exist_ok=True)

    # 保存报告
    report_path = os.path.join(result_dir, "report.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)

    # 保存净值曲线
    for name, nav_df in all_nav.items():
        safe_name = name.replace("/", "_").replace(" ", "_")
        nav_df.to_csv(os.path.join(result_dir, f"{safe_name}_nav.csv"))
        try:
            nav_df.to_parquet(os.path.join(result_dir, f"{safe_name}_nav.parquet"))
        except Exception:
            pass

    print(f"\n✅ 结果已保存: {result_dir}")
    print(f"   报告: {report_path}")

    return all_nav, all_metrics


if __name__ == "__main__":
    main()
