"""
Qlib 回测 CLI 入口 — 委托给 engine/qlib_bridge.py

用法:
  # 数据转换
  python qlib_backtest.py convert               # 全量转换所有股票
  python qlib_backtest.py convert --symbols 500  # 只转500只 (快速测试)
  python qlib_backtest.py convert --force       # 强制重建
  python qlib_backtest.py check                 # 检查数据状态

  # 回测
  python qlib_backtest.py run --strategy 小市值(月)     # 跑单个策略
  python qlib_backtest.py run --strategy Barra四因子
  python qlib_backtest.py run --strategy 红利策略v6(聚宽对齐)

  # 列出可用策略
  python qlib_backtest.py list
"""
import os, sys, argparse

sys.path.insert(0, os.path.dirname(__file__))


def cmd_convert(args):
    """Parquet → Qlib bin 格式转换"""
    from engine.qlib_bridge import ParquetToQlibConverter
    import pandas as pd
    from config import DATA_DIR

    converter = ParquetToQlibConverter()
    symbols = None

    if args.symbols and args.symbols > 0:
        kline = pd.read_parquet(
            os.path.join(DATA_DIR, "kline_adj.parquet"),
            columns=['symbol']
        )
        all_syms = sorted(kline['symbol'].unique())
        step = max(1, len(all_syms) // args.symbols)
        symbols = all_syms[::step][:args.symbols]
        print(f"限制股票池: {len(symbols)} 只 (从 {len(all_syms)} 只中采样)")

    converter.convert_all(symbols=symbols, force=args.force)


def cmd_check(_args):
    """检查 Qlib 数据状态"""
    from engine.qlib_bridge import ParquetToQlibConverter
    converter = ParquetToQlibConverter()
    manifest = converter.read_manifest()

    if manifest:
        print("✅ Qlib 数据已存在:")
        for k, v in manifest.items():
            print(f"   {k}: {v}")
        print(f"   需要更新: {converter.needs_update()}")
    else:
        print("❌ Qlib 数据不存在")
        print("   请运行: python qlib_backtest.py convert")


def cmd_list(_args):
    """列出所有可用策略"""
    from strategies import discover_strategies
    strategies = discover_strategies()
    print(f"发现 {len(strategies)} 个策略:")
    for name in sorted(strategies.keys()):
        print(f"  - {name}")


def cmd_run(args):
    """用 Qlib 引擎跑指定策略"""
    from engine.qlib_bridge import QlibBacktestRunner

    if not args.strategy:
        print("请指定 --strategy")
        print("可用策略列表: python qlib_backtest.py list")
        return

    runner = QlibBacktestRunner()
    nav_df, metrics = runner.run_strategy(
        args.strategy,
        rebalance_freq=args.freq,
        topk=args.topk,
    )

    print(f"\n{'='*50}")
    print(f"📊 {args.strategy}")
    print(f"{'='*50}")
    for k, v in metrics.items():
        print(f"  {k}: {v}")

    if nav_df is not None and len(nav_df) > 1:
        start_val = nav_df['nav'].iloc[0]
        end_val = nav_df['nav'].iloc[-1]
        ret = (end_val / start_val - 1) * 100
        print(f"\n  净值: {start_val:,.0f} → {end_val:,.0f}  ({ret:+.1f}%)")
        print(f"  交易日: {len(nav_df)}")


def main():
    parser = argparse.ArgumentParser(
        description="Qlib 回测 CLI (数据转换 + 回测执行)"
    )
    sub = parser.add_subparsers(dest="cmd", help="子命令")

    # convert
    p_conv = sub.add_parser("convert", help="Parquet → Qlib bin 转换")
    p_conv.add_argument("--symbols", type=int, default=0,
                        help="股票数量 (0=全部, 500=采样)")
    p_conv.add_argument("--force", action="store_true", help="强制重建")

    # check
    sub.add_parser("check", help="检查 Qlib 数据状态")

    # list
    sub.add_parser("list", help="列出可用策略")

    # run
    p_run = sub.add_parser("run", help="用 Qlib 引擎跑回测")
    p_run.add_argument("--strategy", type=str, required=True, help="策略名称")
    p_run.add_argument("--freq", type=int, default=21,
                       help="调仓频率 (交易日, 默认21=月频)")
    p_run.add_argument("--topk", type=int, default=50,
                       help="持仓数量 (默认50)")

    args = parser.parse_args()

    if args.cmd == "convert":
        cmd_convert(args)
    elif args.cmd == "check":
        cmd_check(args)
    elif args.cmd == "list":
        cmd_list(args)
    elif args.cmd == "run":
        cmd_run(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
