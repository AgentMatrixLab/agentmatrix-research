"""
QUANT DESK 后端配置
"""
import os

# ── 数据路径（复用 BigQuant 引擎数据） ──
ENGINE_DIR = r"D:\bigquant\custom_engine"
DATA_DIR = os.path.join(ENGINE_DIR, "data")
RESULTS_DIR = os.path.join(ENGINE_DIR, "results")
STRATEGIES_DIR = os.path.join(ENGINE_DIR, "strategies")

# ── 回测参数 ──
INIT_CAPITAL = 1_000_000
TRADE_FEE_RATE = 0.0003
SLIPPAGE = 0.001
ST_TAX_RATE = 0.001
BACKTEST_YEARS = 5

# ── 数据库 ──
DB_PATH = os.path.join(os.path.dirname(__file__), "bt_panel.db")

# ── 任务队列 ──
QUEUE_DIR = os.path.join(os.path.dirname(__file__), "queue_store")
MAX_CONCURRENT_BACKTESTS = 1        # 同一时间只跑一个回测，防 CPU 打满
BACKTEST_POLL_INTERVAL_S = 1.5      # 前端轮询间隔参考

# ── 缓存 ──
CACHE_TTL_S = 30                    # 持仓/交易等短生命周期缓存
NAV_CACHE_TTL_S = 300               # 净值数据缓存（每日更新后失效）

# ── 内存控制 ──
MAX_PARQUET_ROWS = 3_000_000        # 单次读取 Parquet 上限行数
DB_PAGE_SIZE = 4096
DB_CACHE_SIZE_MB = 32               # SQLite 缓存 32MB，不贪多

# ── 安全 ──
UPLOAD_MAX_SIZE_MB = 1              # 策略文件上限
SANDBOX_TIMEOUT_S = 30              # 沙箱试跑超时
FORBIDDEN_IMPORTS = {"os", "sys", "socket", "requests", "subprocess", "shutil", "ctypes"}
FORBIDDEN_FUNCTIONS = {"open(", "exec(", "eval(", "__import__(", "compile(",
                        "globals()", "locals()", "getattr("}

# ── 基准映射 ──
BENCHMARK_MAP = {
    "csi300": "沪深300",
    "csi500": "中证500",
    "csi1000": "中证1000",
}

# 从日历获得完整交易日列表（惰性）
_calendar = None
def get_calendar():
    global _calendar
    if _calendar is None:
        import pandas as pd
        cal_path = os.path.join(DATA_DIR, "calendar.parquet")
        df = pd.read_parquet(cal_path)
        dates = pd.to_datetime(df["trade_date"]).sort_values()
        _calendar = dates.tolist()
    return _calendar
