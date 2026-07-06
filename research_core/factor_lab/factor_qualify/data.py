"""
数据加载模块 — 统一数据源 + 因子计算接口

数据源：
  - Qlib CSI500 (2010-2020): ~/Desktop/agentmatrix-research/data/qlib/cn_data/
  - OOS (2021-2025): ~/Desktop/GP/oos_ohlcv.csv

因子接口：compute(panel: pd.DataFrame) -> pd.Series
  参考 AgentMatrix submissions/momentum_20d/factor.py
"""

from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd


# ─── 路径配置 ───────────────────────────────────────────────
QLIB_DATA = Path.home() / "Desktop/agentmatrix-research/data/qlib/cn_data"
OOS_CSV = Path.home() / "Desktop/GP/oos_ohlcv.csv"
CSI500_JSON = Path.home() / "Desktop/GP/csi500_industry.json"
RAW_FIELDS = ["open", "close", "high", "low", "volume"]


# ─── Qlib 数据加载 (2010-2020, CSI500) ─────────────────────

def load_qlib_csi500(end_year: int = 2020, max_stocks: int = 500) -> pd.DataFrame:
    """加载 Qlib CSI500 成分股的 OHLCV 数据。

    Args:
        end_year: 数据截止年份（不含）
        max_stocks: 最大股票数

    Returns:
        DataFrame: [date, code, open, high, low, close, volume,
                     change, future_ret_1d, future_ret_5d, future_ret_20d]
    """
    inst_file = QLIB_DATA / "instruments" / "csi500.txt"
    if not inst_file.exists():
        raise FileNotFoundError(f"CSI500 instrument file not found: {inst_file}")
    codes_in = [line.split("\t")[0] for line in inst_file.read_text().splitlines() if line.strip()]

    cal_file = QLIB_DATA / "calendars" / "day.txt"
    cal = cal_file.read_text().splitlines()
    cal_dates = [d for d in cal
                 if d.strip() and "2010-01-01" <= d.strip() <= f"{end_year}-12-31"]

    feat_dir = QLIB_DATA / "features"
    records = []
    loaded = 0

    for ci in codes_in:
        if loaded >= max_stocks:
            break
        code = ci.lower()
        cd = feat_dir / code
        if not cd.exists():
            continue
        series = {}
        ok = True
        for f in RAW_FIELDS:
            fp = cd / f"{f}.day.bin"
            if not fp.exists():
                ok = False
                break
            series[f] = np.fromfile(fp, dtype=np.float32)
        if not ok:
            continue
        try:
            si = cal.index(cal_dates[0])
        except ValueError:
            continue
        avail = min(len(cal_dates), min(len(series[f]) - si for f in RAW_FIELDS))
        if avail < 252:
            continue
        for i in range(avail):
            row = {"date": cal_dates[i], "code": code}
            all_finite = True
            for f in RAW_FIELDS:
                v = float(series[f][si + i])
                if not np.isfinite(v):
                    all_finite = False
                    break
                row[f] = v
            if all_finite:
                records.append(row)
        loaded += 1

    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["code", "date"]).reset_index(drop=True)

    # 衍生列
    df["change"] = df.groupby("code")["close"].pct_change(1)
    df["future_ret_1d"] = df.groupby("code")["close"].pct_change(1).shift(-1)
    df["future_ret_5d"] = df.groupby("code")["close"].pct_change(5).shift(-5)
    df["future_ret_20d"] = df.groupby("code")["close"].pct_change(20).shift(-20)
    for col in RAW_FIELDS + ["change", "future_ret_1d", "future_ret_5d", "future_ret_20d"]:
        df = df[np.isfinite(df[col])]

    return df.reset_index(drop=True)


# ─── OOS 数据加载 (2021-2025) ──────────────────────────────

def load_oos_2021_2025() -> pd.DataFrame:
    """加载 OOS 数据，转换为 Qlib 格式。

    Returns:
        DataFrame: [date, code, open, high, low, close, volume,
                     change, future_ret_1d, future_ret_5d, future_ret_20d]
    """
    if not OOS_CSV.exists():
        raise FileNotFoundError(f"OOS data not found: {OOS_CSV}")
    df = pd.read_csv(OOS_CSV, parse_dates=["date"], skip_blank_lines=True)
    df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
    # SHSE.600006 → sh600006
    df["code"] = (df["symbol"].str.replace("SHSE.", "sh", regex=False)
                  .str.replace("SZSE.", "sz", regex=False).str.lower())
    df = df[["date", "code", "open", "high", "low", "close", "volume"]].copy()
    df = df.sort_values(["code", "date"]).reset_index(drop=True)
    df["change"] = df.groupby("code")["close"].pct_change(1)
    df["future_ret_1d"] = df.groupby("code")["close"].pct_change(1).shift(-1)
    df["future_ret_5d"] = df.groupby("code")["close"].pct_change(5).shift(-5)
    df["future_ret_20d"] = df.groupby("code")["close"].pct_change(20).shift(-20)
    for col in ["change", "future_ret_1d", "future_ret_5d", "future_ret_20d"]:
        df = df[np.isfinite(df[col])]
    return df.reset_index(drop=True)


# ─── 合并全量数据 ──────────────────────────────────────────

def load_full_data() -> pd.DataFrame:
    """加载 2010-2025 全量数据。

    Returns:
        DataFrame: [date, code, open, high, low, close, volume,
                     change, future_ret_1d, future_ret_5d, future_ret_20d]
    """
    df_qlib = load_qlib_csi500(end_year=2020)
    df_oos = load_oos_2021_2025()
    common = ["date", "code", "open", "high", "low", "close", "volume",
              "change", "future_ret_1d", "future_ret_5d", "future_ret_20d"]
    df = pd.concat([df_qlib[common], df_oos[common]], ignore_index=True)
    df = df.sort_values(["code", "date"]).reset_index(drop=True)
    return df


# ─── 因子计算接口 ──────────────────────────────────────────

def compute_factor(panel: pd.DataFrame, factor_fn) -> pd.DataFrame:
    """对 panel 调用因子函数，返回含因子值的 DataFrame。

    Args:
        panel: [date, code, open, high, low, close, volume, ...]
        factor_fn: compute(panel) -> pd.Series 或 compute(panel) -> pd.DataFrame

    Returns:
        panel 加上 factor_value 列
    """
    result = panel.copy()
    output = factor_fn(panel)
    if isinstance(output, pd.DataFrame):
        # 多因子：取第一列
        result["factor_value"] = output.iloc[:, 0].values
    else:
        result["factor_value"] = output.values
    return result
