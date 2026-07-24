"""
全局配置 — 改这里就行
"""
import os

# ========== 雷菱 API ==========
API_BASE = "http://115.159.73.134:8765"
API_TOKEN = "sk-admin-pNxt77hQYi4druTaMnmJz8GxN5rw49I7"

# ========== 本地数据路径 ==========
BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # 自动检测项目根目录
DATA_DIR = os.path.join(BASE_DIR, "data")  # 项目自包含
STRATEGY_DIR = os.path.join(BASE_DIR, "strategies")
RESULTS_DIR = os.path.join(BASE_DIR, "results")
OUTPUT_DIR = RESULTS_DIR  # generate_report 输出目录

# ========== 回测参数 ==========
BACKTEST_YEARS = 5          # 滚动窗口年数
INIT_CAPITAL = 1_000_000    # 初始资金
TRADE_FEE_RATE = 0.0003     # 手续费 万3 (聚宽默认, 双边)
SLIPPAGE = 0.001           # 滑点 0.1%
ST_TAX_RATE = 0.001         # 印花税 千1 (卖出时)
MAX_STOCKS = 50             # 最大持仓数量
BENCHMARK = "000300.SH"     # 基准指数(沪深300)

# ========== 数据范围 ==========
# 全A股: 不限制, 自动从API拉取所有股票
# 如果要限制为某些指数成分股, 改这里
ONLY_CSI_300 = False        # True=只做沪深300
ONLY_CSI_500 = False        # True=只做中证500
ONLY_CSI_1000 = False       # True=只做中证1000

# ========== 复权方式 ==========
# "backward" = 后复权, 价格随分红下修(常用)
# "forward" = 前复权, 价格随分红上修
ADJUST_MODE = "backward"

# ========== Qlib 桥接配置 ==========
QLIB_BIN_DIR = os.path.join(DATA_DIR, "qlib_bin")  # Qlib bin 数据目录
# Qlib 标准特征名 → Parquet 列名 (bin 文件名用 Qlib 标准名, 内容从 Parquet 对应列取)
QLIB_FEATURE_MAP = {
    "close": "close_adj",    # $close  → 后复权收盘价
    "open": "open_adj",      # $open   → 后复权开盘价
    "high": "high_adj",      # $high   → 后复权最高价
    "low": "low_adj",        # $low    → 后复权最低价
    "volume": "volume",      # $volume → 成交量
    "amount": "amount",      # $amount → 成交额
}
