"""
📡 每日数据更新脚本

用法:
  python update_data.py          # 增量更新 (默认)
  python update_data.py --full   # 全量重新拉取

由 cron 每天 10:00 触发
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))

from engine.data_manager import run_full_update


if __name__ == "__main__":
    run_full_update()
