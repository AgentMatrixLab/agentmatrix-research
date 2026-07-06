"""
samzhang8/model 的17个因子 → factor_qualify 可验证格式

每个因子的 compute(panel) 函数。
panel 包含: date, code, open, high, low, close, volume, amount
"""
import pandas as pd
import numpy as np


# ── 1. ret_5d: 5日收益率 ──
def ret_5d(panel):
    p = panel.sort_values(["code", "date"]).reset_index(drop=True)
    r = p.groupby("code")["close"].pct_change(5)
    r.index = p.index
    return r.reindex(panel.index)


# ── 2. ret_1m: 20日收益率 (动量) ──
def ret_1m(panel):
    p = panel.sort_values(["code", "date"]).reset_index(drop=True)
    r = p.groupby("code")["close"].pct_change(20)
    r.index = p.index
    return r.reindex(panel.index)


# ── 3. volatility_1m: 20日波动率 ──
def volatility_1m(panel):
    p = panel.sort_values(["code", "date"]).reset_index(drop=True)
    r = p.groupby("code")["close"].pct_change()
    v = r.groupby(p["code"]).rolling(20).std().reset_index(level=0, drop=True)
    return v.reindex(panel.index)


# ── 4. reversal: -ret_5d (短期反转) ──
def reversal(panel):
    return -ret_5d(panel)


# ── 5. avg_amount_log: log(20日均成交额) ──
def avg_amount_log(panel):
    p = panel.sort_values(["code", "date"]).reset_index(drop=True)
    p["amount_raw"] = p["volume"] * p["close"]
    v = p.groupby("code")["amount_raw"].rolling(20).mean().reset_index(level=0, drop=True)
    result = np.log(v.replace(0, np.nan))
    result.index = p.index
    return result.reindex(panel.index)


# ── 6. max_ret_1m: 20日最大日收益 ──
def max_ret_1m(panel):
    p = panel.sort_values(["code", "date"]).reset_index(drop=True)
    r = p.groupby("code")["close"].pct_change()
    v = r.groupby(p["code"]).rolling(20).max().reset_index(level=0, drop=True)
    return v.reindex(panel.index)


# ── 7. min_ret_1m: 20日最小日收益 ──
def min_ret_1m(panel):
    p = panel.sort_values(["code", "date"]).reset_index(drop=True)
    r = p.groupby("code")["close"].pct_change()
    v = r.groupby(p["code"]).rolling(20).min().reset_index(level=0, drop=True)
    return v.reindex(panel.index)


# ── 8. up_ratio_1m: 20日上涨比例 ──
def up_ratio_1m(panel):
    p = panel.sort_values(["code", "date"]).reset_index(drop=True)
    r = p.groupby("code")["close"].pct_change()
    up = (r > 0).astype(float)
    v = up.groupby(p["code"]).rolling(20).mean().reset_index(level=0, drop=True)
    return v.reindex(panel.index)


# ── 9. bb_position: 布林带位置 ──
def bb_position(panel):
    p = panel.sort_values(["code", "date"]).reset_index(drop=True)
    ma20 = p.groupby("code")["close"].rolling(20).mean().reset_index(level=0, drop=True)
    std20 = p.groupby("code")["close"].rolling(20).std().reset_index(level=0, drop=True)
    r = (p["close"] - ma20) / std20.replace(0, np.nan)
    r.index = p.index
    return r.reindex(panel.index)


# ── 10. rsi_14: 14日RSI ──
def rsi_14(panel):
    p = panel.sort_values(["code", "date"]).reset_index(drop=True)
    delta = p.groupby("code")["close"].diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.groupby(p["code"]).rolling(14).mean().reset_index(level=0, drop=True)
    avg_loss = loss.groupby(p["code"]).rolling(14).mean().reset_index(level=0, drop=True)
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - 100 / (1 + rs)
    rsi.index = p.index
    return rsi.reindex(panel.index)


# ── 11. amplitude_1m: 20日平均振幅 ──
def amplitude_1m(panel):
    p = panel.sort_values(["code", "date"]).reset_index(drop=True)
    amp = (p["high"] - p["low"]) / p["close"]
    v = amp.groupby(p["code"]).rolling(20).mean().reset_index(level=0, drop=True)
    return v.reindex(panel.index)


# ── 12. high_low_1m: 20日高低价差 ──
def high_low_1m(panel):
    p = panel.sort_values(["code", "date"]).reset_index(drop=True)
    h = p.groupby("code")["high"].rolling(20).max().reset_index(level=0, drop=True)
    l = p.groupby("code")["low"].rolling(20).min().reset_index(level=0, drop=True)
    r = (h - l) / p["close"]
    r.index = p.index
    return r.reindex(panel.index)


# ── 13. illiquidity: 20日非流动性 ──
def illiquidity(panel):
    p = panel.sort_values(["code", "date"]).reset_index(drop=True)
    p["amount_raw"] = p["volume"] * p["close"]
    daily_ret = np.abs(p.groupby("code")["close"].pct_change())
    daily_ret.index = p.index
    r = daily_ret.reindex(panel.index)
    v = (r / p["amount_raw"]).groupby(p["code"]).rolling(20).mean().reset_index(level=0, drop=True)
    return v.reindex(panel.index)


# ── 14. vol_convergence: 成交量短期/长期比 ──
def vol_convergence(panel):
    p = panel.sort_values(["code", "date"]).reset_index(drop=True)
    sv = p.groupby("code")["volume"].rolling(5).mean().reset_index(level=0, drop=True)
    lv = p.groupby("code")["volume"].rolling(20).mean().reset_index(level=0, drop=True)
    r = sv / lv.replace(0, np.nan)
    r.index = p.index
    return r.reindex(panel.index)


# ── 15. volume_ratio: 当日成交量/5日均量 ──
def volume_ratio(panel):
    p = panel.sort_values(["code", "date"]).reset_index(drop=True)
    mv = p.groupby("code")["volume"].shift(1).rolling(5).mean().reset_index(level=0, drop=True)
    r = p["volume"] / mv.replace(0, np.nan)
    r.index = p.index
    return r.reindex(panel.index)


# ── 16. turnover: 20日换手率 ──
def turnover(panel):
    p = panel.sort_values(["code", "date"]).reset_index(drop=True)
    p["amount_raw"] = p["volume"] * p["close"]
    r = p.groupby("code")["amount_raw"].rolling(20).mean().reset_index(level=0, drop=True)
    r.index = p.index
    return r.reindex(panel.index)


# ── 17. ret_vol_adj: 20日收益/波动率比 ──
def ret_vol_adj(panel):
    p = panel.sort_values(["code", "date"]).reset_index(drop=True)
    ret20 = p.groupby("code")["close"].pct_change(20)
    daily_ret = p.groupby("code")["close"].pct_change()
    vol20 = daily_ret.groupby(p["code"]).rolling(20).std().reset_index(level=0, drop=True)
    r = ret20 / vol20.replace(0, np.nan)
    r.index = p.index
    return r.reindex(panel.index)


# ── 因子注册表 ──
ALL_FACTORS = {
    "ret_5d": ret_5d,
    "ret_1m": ret_1m,
    "volatility_1m": volatility_1m,
    "reversal": reversal,
    "avg_amount_log": avg_amount_log,
    "max_ret_1m": max_ret_1m,
    "min_ret_1m": min_ret_1m,
    "up_ratio_1m": up_ratio_1m,
    "bb_position": bb_position,
    "rsi_14": rsi_14,
    "amplitude_1m": amplitude_1m,
    "high_low_1m": high_low_1m,
    "illiquidity": illiquidity,
    "vol_convergence": vol_convergence,
    "volume_ratio": volume_ratio,
    "turnover": turnover,
    "ret_vol_adj": ret_vol_adj,
}
