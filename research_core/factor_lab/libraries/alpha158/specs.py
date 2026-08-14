"""
Alpha158 因子规格说明

每个因子的公式、含义和所属分类。
因子定义来源: Qlib qlib/contrib/data/loader.py Alpha158DL
"""
import numpy as np

FACTOR_SPECS = {}

# ---- K-bar 形态因子 (9) ----
_kbar_specs = {
    "KMID":  "中位价涨跌幅: (close - open) / open",
    "KLEN":  "K线振幅: (high - low) / open",
    "KMID2": "中位价归一化: (close - open) / (high - low + eps)",
    "KUP":   "上影线占比: (high - max(open,close)) / open",
    "KUP2":  "上影线归一化: (high - max(open,close)) / (high - low + eps)",
    "KLOW":  "下影线占比: (min(open,close) - low) / open",
    "KLOW2": "下影线归一化: (min(open,close) - low) / (high - low + eps)",
    "KSFT":  "价格偏移: (2*close - high - low) / open",
    "KSFT2": "价格偏移归一化: (2*close - high - low) / (high - low + eps)",
}
FACTOR_SPECS.update(_kbar_specs)

# ---- Price 价格比率因子 (4) ----
FACTOR_SPECS.update({
    "OPEN0": "开盘价/收盘价: open / close",
    "HIGH0": "最高价/收盘价: high / close",
    "LOW0":  "最低价/收盘价: low / close",
    "VWAP0": "均价/收盘价: vwap / close",
})

# ---- Rolling 滚动窗口因子 (29 × 5) ----
WINDOWS = [5, 10, 20, 30, 60]

_rolling_specs = {
    "ROC":   "收益率: Ref(close, d) / close (滞后d日的收盘价 / 当前收盘价)",
    "MA":    "均线比: Mean(close, d) / close",
    "STD":   "波动率: Std(close, d) / close",
    "BETA":  "斜率: 收盘价对时间的线性回归斜率 / close",
    "RSQR":  "拟合优度: 收盘价对时间线性回归的 R-squared",
    "RESI":  "残差: 线性回归残差 / close",
    "MAX":   "最高价比: Max(high, d) / close",
    "MIN":   "最低价比: Min(low, d) / close",
    "QTLU":  "上分位比: Quantile(close, d, 0.8) / close",
    "QTLD":  "下分位比: Quantile(close, d, 0.2) / close",
    "RANK":  "时序排名: 当前收盘价在窗口内的百分位 (0~1)",
    "RSV":   "RSV指标: (close - Min(low,d)) / (Max(high,d) - Min(low,d))",
    "IMAX":  "最大值位置: IdxMax(high, d) / d (最近高点距今时间占比)",
    "IMIN":  "最小值位置: IdxMin(low, d) / d (最近低点距今时间占比)",
    "IMXD":  "极值位置差: (IdxMax(high,d) - IdxMin(low,d)) / d",
    "CORR":  "价量相关: 收盘价与 log(volume+1) 的滚动 Pearson 相关系数",
    "CORD":  "收益-量变相关: 日收益率与 log(量比+1) 的滚动相关系数",
    "CNTP":  "上涨天数占比: 窗口内收盘价>前日的天数 / d",
    "CNTN":  "下跌天数占比: 窗口内收盘价<前日的天数 / d",
    "CNTD":  "涨跌天数差: CNTP - CNTN",
    "SUMP":  "涨幅占比: 窗口内正收益之和 / 绝对收益之和",
    "SUMN":  "跌幅占比: 窗口内负收益之和(正值) / 绝对收益之和",
    "SUMD":  "涨跌幅差: SUMP - SUMN",
    "VMA":   "量均线比: Mean(volume, d) / volume",
    "VSTD":  "量波动: Std(volume, d) / volume",
    "WVMA":  "加权量波动: Std(|ret|*vol, d) / Mean(|ret|*vol, d)",
    "VSUMP": "量涨幅占比: 窗口内量增之和 / 绝对量变之和",
    "VSUMN": "量跌幅占比: 窗口内量减之和 / 绝对量变之和",
    "VSUMD": "量涨跌差: VSUMP - VSUMN",
}

for name_prefix, desc in _rolling_specs.items():
    for d in WINDOWS:
        FACTOR_SPECS[f"{name_prefix}{d}"] = f"{desc} (窗口 d={d})"


def get_spec(factor_name):
    """获取单个因子的规格说明"""
    return FACTOR_SPECS.get(factor_name, "未定义")


def get_all_specs():
    """获取所有因子的规格说明"""
    return FACTOR_SPECS.copy()
