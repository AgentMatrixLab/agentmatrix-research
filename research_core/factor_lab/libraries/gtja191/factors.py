from __future__ import annotations

import importlib
import numpy as np
import pandas as pd
from alpha.context import ExecContext


IMPLEMENTED_GTJA191_FACTORS = tuple(f"alpha{i}" for i in range(1, 192))


def _alpha_number(name: str) -> int:
    if not name.startswith("alpha"):
        raise ValueError(f"Invalid GTJA191 factor name: {name}")
    number = int(name[5:])
    if number < 1 or number > 191:
        raise ValueError(f"Invalid GTJA191 factor name: {name}")
    return number


def _prepare_frame(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str], list[pd.Timestamp]]:
    data = df.copy()
    data["date"] = pd.to_datetime(data["date"])
    required = ["date", "code", "open", "high", "low", "close", "volume"]
    missing = [col for col in required if col not in data.columns]
    if missing:
        raise ValueError(f"GTJA191 input missing columns: {missing}")
    if "amount" not in data.columns:
        data["amount"] = data["close"] * data["volume"]
    if "vwap" not in data.columns:
        data["vwap"] = data["amount"] / data["volume"].replace(0, np.nan)
    codes = sorted(data["code"].dropna().astype(str).unique().tolist())
    dates = sorted(pd.to_datetime(data["date"].dropna().unique()).tolist())
    idx = pd.MultiIndex.from_product([codes, dates], names=["code", "date"])
    data = data.assign(code=data["code"].astype(str)).set_index(["code", "date"]).sort_index().reindex(idx)
    frame = pd.DataFrame({
        "securityid": idx.get_level_values("code"),
        "tradetime": idx.get_level_values("date"),
        "open": data["open"].to_numpy(dtype=float),
        "high": data["high"].to_numpy(dtype=float),
        "low": data["low"].to_numpy(dtype=float),
        "close": data["close"].to_numpy(dtype=float),
        "vol": data["volume"].to_numpy(dtype=float),
        "vwap": data["vwap"].to_numpy(dtype=float),
        "cap": data.get("cap", data["amount"]).to_numpy(dtype=float),
    })
    return frame, codes, dates


def _gtja_sma_flat(values: np.ndarray, n: int, m: int, codes: list[str], dates: list[pd.Timestamp]) -> np.ndarray:
    arr = np.asarray(values, dtype=float).reshape((len(codes), len(dates)))
    out = np.full_like(arr, np.nan, dtype=float)
    for row_idx in range(arr.shape[0]):
        prev = np.nan
        started = False
        for col_idx, value in enumerate(arr[row_idx]):
            if np.isfinite(value):
                prev = value if not started or not np.isfinite(prev) else (value * m + prev * (n - m)) / n
                started = True
                out[row_idx, col_idx] = prev
            elif started:
                out[row_idx, col_idx] = prev
    return out.ravel()


def _gtja_ma_flat(values: np.ndarray, n: int, codes: list[str], dates: list[pd.Timestamp]) -> np.ndarray:
    arr = np.asarray(values, dtype=float).reshape((len(codes), len(dates)))
    out = np.full_like(arr, np.nan, dtype=float)
    for row_idx in range(arr.shape[0]):
        series = pd.Series(arr[row_idx])
        out[row_idx] = series.rolling(n, min_periods=n).mean().to_numpy(dtype=float)
    return out.ravel()


def _gtja_filtered_regbeta_flat(y: np.ndarray, x: np.ndarray, cond: np.ndarray, window: int, codes: list[str], dates: list[pd.Timestamp]) -> np.ndarray:
    y_arr = np.asarray(y, dtype=float).reshape((len(codes), len(dates)))
    x_arr = np.asarray(x, dtype=float).reshape((len(codes), len(dates)))
    cond_arr = np.asarray(cond, dtype=bool).reshape((len(codes), len(dates)))
    out = np.full_like(y_arr, np.nan, dtype=float)
    effective_window = min(int(window), y_arr.shape[1])
    min_valid = max(30, int(effective_window * 0.3))
    for row_idx in range(y_arr.shape[0]):
        for col_idx in range(effective_window - 1, y_arr.shape[1]):
            sl = slice(col_idx - effective_window + 1, col_idx + 1)
            mask = cond_arr[row_idx, sl] & np.isfinite(y_arr[row_idx, sl]) & np.isfinite(x_arr[row_idx, sl])
            if mask.sum() < min_valid:
                continue
            yy = y_arr[row_idx, sl][mask]
            xx = x_arr[row_idx, sl][mask]
            var = np.var(xx)
            if var <= 0 or not np.isfinite(var):
                continue
            out[row_idx, col_idx] = np.cov(xx, yy, ddof=0)[0, 1] / var
    return out.ravel()


def _make_context(frame: pd.DataFrame) -> ExecContext:
    ctx = ExecContext(frame)
    close = frame["close"].to_numpy(dtype=float)
    grouped = frame.groupby("tradetime", sort=False)
    ctx.BANCHMARKINDEXCLOSE = grouped["close"].transform("mean").to_numpy(dtype=float)
    ctx.BENCHMARKINDEXCLOSE = ctx.BANCHMARKINDEXCLOSE
    ctx.BANCHMARKINDEXOPEN = grouped["open"].transform("mean").to_numpy(dtype=float)
    ctx.BENCHMARKINDEXOPEN = ctx.BANCHMARKINDEXOPEN
    with np.errstate(divide="ignore", invalid="ignore"):
        ctx.MKT = ctx.BANCHMARKINDEXCLOSE / ctx.DELAY(ctx.BANCHMARKINDEXCLOSE, 1) - 1
    ctx.SMB = np.zeros_like(close, dtype=float)
    ctx.HML = np.zeros_like(close, dtype=float)
    return ctx


def _result_frame(values: np.ndarray, codes: list[str], dates: list[pd.Timestamp], factor_name: str) -> pd.DataFrame:
    arr = np.asarray(values, dtype=float).reshape((len(codes), len(dates)))
    return pd.DataFrame({
        "date": np.tile(dates, len(codes)),
        "code": np.repeat(codes, len(dates)),
        factor_name: arr.ravel(),
    })[["date", "code", factor_name]]


def compute_gtja191_alphas(df: pd.DataFrame, factor_names: list[str] | None = None) -> pd.DataFrame:
    requested = list(factor_names or IMPLEMENTED_GTJA191_FACTORS)
    invalid = [name for name in requested if name not in IMPLEMENTED_GTJA191_FACTORS]
    if invalid:
        raise ValueError(f"Unsupported GTJA191 factors: {invalid}")
    frame, codes, dates = _prepare_frame(df)
    ctx = _make_context(frame)
    ctx.SMA = lambda values, n, m=None: _gtja_sma_flat(values, int(n), int(m), codes, dates) if m is not None else _gtja_ma_flat(values, int(n), codes, dates)
    ctx.GTJA_FILTERED_REGBETA = lambda y, x, cond, window: _gtja_filtered_regbeta_flat(y, x, cond, int(window), codes, dates)
    alpha_mod = importlib.import_module("research_core.factor_lab.libraries.gtja191.vendor.alpha_lib_gtja191.alpha191")
    result = pd.DataFrame({"date": np.tile(dates, len(codes)), "code": np.repeat(codes, len(dates))})
    for factor_name in requested:
        fn = getattr(alpha_mod, f"alpha_{_alpha_number(factor_name):03d}")
        factor_frame = _result_frame(fn(ctx), codes, dates, factor_name)
        result = result.merge(factor_frame, on=["date", "code"], how="left")
    for factor_name in requested:
        result[factor_name] = result[factor_name].replace([np.inf, -np.inf], np.nan)
    return result
