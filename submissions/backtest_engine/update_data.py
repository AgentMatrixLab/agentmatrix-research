"""
📡 一键数据更新入口 ── CH全量 + SIM增量

用法:
  python update_data.py              # 智能判断: 无数据→全量初始化, 有数据→每日增量
  python update_data.py --full       # 强制全量从CH重新拉取
  python update_data.py --report     # 只查看数据状态
  python update_data.py --skip-qlib  # 跳过Qlib bin重建(提速)

数据流:
  首次:
    CH (/ch/*)  → 全量K线 + 复权因子 + 交易日历 + ST/停牌 + 财报
    → 合并后复权 → kline_adj.parquet
    → Qlib .bin 格式

  每日:
    SIM (/sim/*) → 最新60天K线 + 估值因子 + 股本市值
    → merge 到 kline_1d.parquet
    → 重新合并复权 → kline_adj.parquet
    → 增量更新 Qlib bin

在Windows任务计划中添加:
  schtasks /create /tn "custom_engine_daily_sync" /tr "python E:\custom_engine\update_data.py" /sc daily /st 18:35
"""
import os, sys, argparse

sys.path.insert(0, os.path.dirname(__file__))
from config import DATA_DIR
from engine.data_manager import DataManager


def main():
    parser = argparse.ArgumentParser(
        description="custom_engine 数据更新",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python update_data.py              智能同步 (首次→全量, 后续→增量)
  python update_data.py --full       强制全量重新拉取
  python update_data.py --report     只看数据状态
  python update_data.py --skip-qlib  跳过Qlib重建 (调试用)
        """,
    )
    parser.add_argument("--full", action="store_true",
                        help="强制全量从 CH 重新拉取")
    parser.add_argument("--report", action="store_true",
                        help="只查看数据状态, 不更新")
    parser.add_argument("--skip-qlib", action="store_true",
                        help="跳过 Qlib bin 重建")
    args = parser.parse_args()

    dm = DataManager()

    if args.report:
        dm.report()
        return

    if args.full:
        print("[强制全量] 从 CH 重新拉取全部历史数据...")
        dm.init_full(force=True)
    else:
        # 智能判断: 无数据 → 全量, 有数据 → 增量
        kline_path = os.path.join(DATA_DIR, "kline_1d.parquet")
        if not os.path.exists(kline_path):
            print("=" * 55)
            print("  🆕 首次运行 — 未检测到本地数据")
            print("  将执行全量初始化 (预计 5-10 分钟)")
            print("=" * 55)
            dm.init_full()
        else:
            # 检查是否需要更新
            if dm.needs_update():
                print("[增量同步] SIM 有新数据, 开始更新...")
                dm.daily_sync(skip_qlib=args.skip_qlib)
            else:
                print("[数据已最新] 无需更新")
                dm.report()



if __name__ == "__main__":
    main()
