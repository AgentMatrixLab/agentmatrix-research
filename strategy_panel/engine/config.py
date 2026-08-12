"""
全局配置 — 改这里就行
"""
import os

# ========== 雷菱 API ==========
API_BASE = "http://115.159.73.134:8765"
API_TOKEN = "sk-admin-pNxt77hQYi4druTaMnmJz8GxN5rw49I7"

# ========== 本地数据路径 ==========
BASE_DIR = r"D:/bigquant/custom_engine"
DATA_DIR = os.path.join(BASE_DIR, "data")
STRATEGY_DIR = os.path.join(BASE_DIR, "strategies")
RESULTS_DIR = os.path.join(BASE_DIR, "results")

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
