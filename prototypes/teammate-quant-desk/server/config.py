"""
QUANT DESK 配置 — 环境变量驱动，路径便携
"""
import os

# ── 数据路径 → 用环境变量 QUANT_DATA_DIR 指向 K 线数据目录 ──
# 同事只需把 kline_1d.parquet 放到 data/ 目录下即可
DATA_DIR = os.environ.get("QUANT_DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "data"))

# ── 回测参数 ──
INIT_CAPITAL = 1_000_000
TRADE_FEE_RATE = 0.0003
SLIPPAGE = 0.001
ST_TAX_RATE = 0.001

# ── 数据库 ──
DB_PATH = os.path.join(os.path.dirname(__file__), "bt_panel.db")

# ── 任务队列 ──
MAX_CONCURRENT_BACKTESTS = 1
BACKTEST_POLL_INTERVAL_S = 1.5

# ── 内存控制 ──
DB_PAGE_SIZE = 4096
DB_CACHE_SIZE_MB = 32

# ── 安全 ──
UPLOAD_MAX_SIZE_MB = 1
SANDBOX_TIMEOUT_S = 30
FORBIDDEN_IMPORTS = {"os", "sys", "socket", "requests", "subprocess", "shutil", "ctypes"}
FORBIDDEN_FUNCTIONS = {"open(", "exec(", "eval(", "__import__(", "compile(",
                        "globals()", "locals()", "getattr("}

# ── 基准映射 ──
BENCHMARK_MAP = {
    "csi300": "沪深300",
    "csi500": "中证500",
    "csi1000": "中证1000",
}
