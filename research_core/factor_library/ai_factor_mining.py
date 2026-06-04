"""Rule-based AI factor mining prototype.

This module mimics an AI-generated factor workflow without calling external
LLM APIs. The generator can later be replaced by an LLM-backed implementation
that emits the same ``CandidateFactor`` objects.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .operators import cross_sectional_rank
from .validation import compute_forward_returns, compute_ic_series, summarize_ic


@dataclass(frozen=True)
class CandidateFactor:
    """Candidate factor metadata and expression label."""

    name: str
    expression: str
    description: str


def generate_candidate_factors() -> list[CandidateFactor]:
    """Return a small set of rule-generated price-volume candidate factors."""
    return [
        CandidateFactor("ai_mom_5d", "rank(close / delay(close, 5) - 1)", "Five-day momentum"),
        CandidateFactor("ai_volume_surge_20d", "rank(volume / ts_mean(volume, 20))", "Volume surge vs 20-day average"),
        CandidateFactor("ai_intraday_return", "rank((close - open) / open)", "Intraday return"),
        CandidateFactor("ai_range_ratio", "rank((high - low) / close)", "Daily range scaled by close"),
        CandidateFactor("ai_vwap_discount", "rank(vwap - close)", "VWAP minus close"),
        CandidateFactor("ai_ma_spread_5_20", "rank(ts_mean(close, 5) / ts_mean(close, 20) - 1)", "Short/long moving-average spread"),
        CandidateFactor("ai_delta_close_5d", "rank(delta(close, 5))", "Five-day close delta"),
        CandidateFactor("ai_volatility_20d", "rank(ts_std(close / delay(close, 1) - 1, 20))", "Twenty-day return volatility"),
    ]


def _safe_vwap(df: pd.DataFrame) -> pd.Series:
    vwap = df["amount"] / df["volume"].replace(0, np.nan)
    fallback = (df["open"] + df["high"] + df["low"] + df["close"]) / 4
    return vwap.replace([np.inf, -np.inf], np.nan).fillna(fallback)


def compute_candidate_factor(df: pd.DataFrame, candidate: CandidateFactor) -> pd.DataFrame:
    """Compute one supported candidate factor from OHLCV input."""
    data = df.sort_values(["code", "date"]).copy()
    by_code = data.groupby("code")

    if candidate.name == "ai_mom_5d":
        raw = data["close"] / by_code["close"].shift(5) - 1
    elif candidate.name == "ai_volume_surge_20d":
        raw = data["volume"] / by_code["volume"].transform(lambda x: x.rolling(20).mean())
    elif candidate.name == "ai_intraday_return":
        raw = (data["close"] - data["open"]) / data["open"].replace(0, np.nan)
    elif candidate.name == "ai_range_ratio":
        raw = (data["high"] - data["low"]) / data["close"].replace(0, np.nan)
    elif candidate.name == "ai_vwap_discount":
        raw = _safe_vwap(data) - data["close"]
    elif candidate.name == "ai_ma_spread_5_20":
        ma5 = by_code["close"].transform(lambda x: x.rolling(5).mean())
        ma20 = by_code["close"].transform(lambda x: x.rolling(20).mean())
        raw = ma5 / ma20 - 1
    elif candidate.name == "ai_delta_close_5d":
        raw = by_code["close"].diff(5)
    elif candidate.name == "ai_volatility_20d":
        ret = data["close"] / by_code["close"].shift(1) - 1
        raw = ret.groupby(data["code"]).transform(lambda x: x.rolling(20).std())
    else:
        raise ValueError(f"Unsupported candidate factor: {candidate.name}")

    data["_raw_factor"] = raw.replace([np.inf, -np.inf], np.nan)
    data[candidate.name] = cross_sectional_rank(data, "date", "_raw_factor")
    return data[["date", "code", candidate.name]]


def mine_and_validate_factors(
    df: pd.DataFrame,
    forward_periods: int = 20,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Generate candidate factors, compute them, and rank by IC summary.

    Returns
    -------
    factor_panel:
        Wide panel with date, code, and candidate factor columns.
    ic_series:
        Date-by-factor Spearman IC observations.
    summary:
        IC summary sorted by descending mean IC.
    """
    candidates = generate_candidate_factors()
    factor_panel = df[["date", "code"]].drop_duplicates().copy()

    for candidate in candidates:
        computed = compute_candidate_factor(df, candidate)
        factor_panel = factor_panel.merge(computed, on=["date", "code"], how="left")

    forward_returns = compute_forward_returns(df, periods=forward_periods)
    factor_names = [candidate.name for candidate in candidates]
    ic_series = compute_ic_series(factor_panel, forward_returns, factor_names)
    summary = summarize_ic(ic_series).sort_values("mean_ic", ascending=False, na_position="last")
    return factor_panel, ic_series, summary.reset_index(drop=True)

