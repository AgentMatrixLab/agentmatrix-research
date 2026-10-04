"""
全局配置 — 改这里就行
"""
import os

# ========== 雷菱 API ==========
# 不在此处内置任何地址或令牌：请通过环境变量提供
#   QUANT_API_BASE  例如 http://<host>:8765
#   QUANT_API_TOKEN
API_BASE = os.environ.get("QUANT_API_BASE", "").rstrip("/")
API_TOKEN = os.environ.get("QUANT_API_TOKEN", "")


def require_api() -> tuple[str, str]:
    """返回 (API_BASE, API_TOKEN)；未配置时直接报错，避免静默打到错误地址。"""
    if not API_BASE or not API_TOKEN:
        raise RuntimeError(
            "QUANT_API_BASE / QUANT_API_TOKEN 未设置；本仓库不内置服务器地址与令牌"
        )
    return API_BASE, API_TOKEN

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
