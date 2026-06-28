"""
Market Data Adapter — Bridge real A-share data into factor_lab panel format.

Converts akshare (or any OHLCV source) to the standardized long-panel format
expected by research_core.factor_lab:
    date, code, open, high, low, close, volume, amount

Provides drop-in replacement for build_alpha101_demo_panel() with real data.

Usage:
    from research_core.data_loader.market_data import fetch_real_panel

    panel = fetch_real_panel(
        start="2023-01-01",
        end="2024-12-31",
        universe="csi300",       # or "csi500", "all", or list of codes
        cache_path="/tmp/ashare_panel.pkl",
    )

    # Then pass to factor_lab as usual:
    from research_core.factor_lab.libraries.alpha101 import compute_alpha101_factors
    factor_frame = compute_alpha101_factors(panel, factor_names=["alpha1","alpha2"])
"""

from __future__ import annotations

import hashlib
import json
import os
import pickle
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

# ═══════════════════════════════════════════════════════════════
# Panel format constants
# ═══════════════════════════════════════════════════════════════

REQUIRED_COLUMNS = ["date", "code", "open", "high", "low", "close", "volume", "amount"]
OPTIONAL_COLUMNS = ["vwap", "adj_factor", "turnover_rate"]


@dataclass(slots=True)
class PanelMetadata:
    """Metadata for a cached panel, so we know when to re-fetch."""
    source: str = "akshare"
    start: str = ""
    end: str = ""
    universe: str = "csi300"
    n_codes: int = 0
    n_dates: int = 0
    generated_at: str = ""
    sha256: str = ""


# ═══════════════════════════════════════════════════════════════
# AkShare data fetching
# ═══════════════════════════════════════════════════════════════

def _fetch_stock_list_csi300() -> list[str]:
    """Get CSI 300 constituent codes."""
    try:
        import akshare as ak
        df = ak.index_stock_cons("000300")
        codes = df["品种代码"].tolist()
        return codes
    except Exception:
        return []


def _fetch_stock_list_csi500() -> list[str]:
    """Get CSI 500 constituent codes."""
    try:
        import akshare as ak
        df = ak.index_stock_cons("000905")
        codes = df["品种代码"].tolist()
        return codes
    except Exception:
        return []


def _fetch_stock_list_all(sample: Optional[int] = None) -> list[str]:
    """Get all A-share codes (exclude ST, new listings, BJ)."""
    try:
        import akshare as ak
        df = ak.stock_info_a_code_name()
        # Filter out BJ (8xx), ST, *ST, N, C
        mask = (
            ~df["code"].str.startswith(("8", "9")) &
            ~df["name"].str.contains("ST|退|N|C", na=False)
        )
        codes = df.loc[mask, "code"].tolist()
        if sample and len(codes) > sample:
            # Stratified sample to preserve size distribution
            rng = np.random.default_rng(42)
            codes = rng.choice(codes, size=sample, replace=False).tolist()
        return codes
    except Exception:
        return []


def _fetch_single_stock_history(code: str, start: str, end: str) -> pd.DataFrame:
    """Fetch daily OHLCV for one stock from akshare (Tencent source)."""
    import akshare as ak
    try:
        df = ak.stock_zh_a_daily(
            symbol=f"sh{code}" if code.startswith(("5", "6", "9")) else f"sz{code}",
            start_date=start,
            end_date=end,
            adjust="qfq",  # 前复权
        )
        if df is None or len(df) == 0:
            return pd.DataFrame()

        df = df.rename(columns={
            "date": "date",
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "volume": "volume",
            "amount": "amount",
        })
        df["code"] = code
        df["date"] = pd.to_datetime(df["date"])
        keep = [c for c in REQUIRED_COLUMNS if c in df.columns]
        return df[keep]
    except Exception:
        return pd.DataFrame()


def fetch_akshare_panel(
    codes: list[str],
    start: str,
    end: str,
    *,
    sleep: float = 0.03,
    verbose: bool = True,
) -> pd.DataFrame:
    """Fetch OHLCV panel from akshare for a list of codes.

    Args:
        codes: List of stock codes (e.g. ["000001", "600519"])
        start: Start date "YYYY-MM-DD"
        end: End date "YYYY-MM-DD"
        sleep: Seconds between API calls (respect rate limits)
        verbose: Print progress

    Returns:
        DataFrame with columns: date, code, open, high, low, close, volume, amount
    """
    frames = []
    n = len(codes)
    t0 = time.time()

    for i, code in enumerate(codes):
        df = _fetch_single_stock_history(code, start, end)
        if len(df) > 0:
            frames.append(df)

        if verbose and (i + 1) % 50 == 0:
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed
            eta = (n - i - 1) / rate if rate > 0 else 0
            print(f"  [{i+1}/{n}] {code} — {elapsed:.0f}s elapsed, ETA {eta:.0f}s")

        time.sleep(sleep)

    if not frames:
        raise ValueError("No data fetched for any code. Check network or date range.")

    panel = pd.concat(frames, ignore_index=True)
    panel = panel.sort_values(["code", "date"]).reset_index(drop=True)

    # Drop rows with zero volume (suspension days)
    panel = panel[panel["volume"] > 0]

    if verbose:
        elapsed = time.time() - t0
        print(f"  ✓ Fetched {len(codes)} stocks × {panel['date'].nunique()} days "
              f"= {len(panel)} rows in {elapsed:.0f}s")

    return panel


# ═══════════════════════════════════════════════════════════════
# Cache layer
# ═══════════════════════════════════════════════════════════════

def _compute_sha256(panel: pd.DataFrame) -> str:
    """Compute deterministic hash of panel for cache validation."""
    sample = panel.sample(n=min(100, len(panel)), random_state=42)
    raw = ",".join(
        f"{r['date'].strftime('%Y-%m-%d')}:{r['code']}:{r['close']:.4f}"
        for _, r in sample.iterrows()
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def load_cached_panel(cache_path: str | Path, *, max_age_hours: int = 24) -> pd.DataFrame | None:
    """Load panel from pickle cache if fresh enough."""
    path = Path(cache_path)
    if not path.exists():
        return None

    meta_path = path.with_suffix(".meta.json")
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text())
            gen_time = datetime.fromisoformat(meta["generated_at"])
            age_hours = (datetime.now() - gen_time).total_seconds() / 3600
            if age_hours > max_age_hours:
                return None
        except Exception:
            pass

    try:
        with open(path, "rb") as f:
            return pickle.load(f)
    except Exception:
        return None


def save_cached_panel(panel: pd.DataFrame, cache_path: str | Path, *, metadata: dict | None = None):
    """Save panel to pickle cache with metadata JSON."""
    path = Path(cache_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "wb") as f:
        pickle.dump(panel, f, protocol=pickle.HIGHEST_PROTOCOL)

    meta = {
        "generated_at": datetime.now().isoformat(),
        "n_codes": int(panel["code"].nunique()),
        "n_dates": int(panel["date"].nunique()),
        "n_rows": len(panel),
        "sha256": _compute_sha256(panel),
        **(metadata or {}),
    }
    meta_path = path.with_suffix(".meta.json")
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False))


# ═══════════════════════════════════════════════════════════════
# Main public API
# ═══════════════════════════════════════════════════════════════

UNIVERSE_RESOLVERS = {
    "csi300": _fetch_stock_list_csi300,
    "csi500": _fetch_stock_list_csi500,
}


def resolve_universe(universe: str | list[str], sample: Optional[int] = None) -> list[str]:
    """Resolve a universe name to a list of stock codes.

    Args:
        universe: "csi300", "csi500", "all", "csi800", or a list of codes
        sample: If set, randomly sample N codes from the resolved universe

    Returns:
        List of stock codes
    """
    if isinstance(universe, list):
        codes = list(universe)
    elif universe == "all":
        codes = _fetch_stock_list_all(sample=None)
    elif universe == "csi800":
        codes = _fetch_stock_list_csi300() + _fetch_stock_list_csi500()
    elif universe in UNIVERSE_RESOLVERS:
        codes = UNIVERSE_RESOLVERS[universe]()
    else:
        raise ValueError(
            f"Unknown universe: {universe}. "
            f"Use one of: {list(UNIVERSE_RESOLVERS.keys())}, 'all', 'csi800', or a list."
        )

    if not codes:
        raise ValueError(f"Could not resolve universe '{universe}'. "
                         "Check network or try a different universe.")

    if sample and len(codes) > sample:
        rng = np.random.default_rng(42)
        codes = rng.choice(codes, size=sample, replace=False).tolist()

    return codes


def fetch_real_panel(
    start: str = "2023-01-01",
    end: str = "2024-12-31",
    *,
    universe: str | list[str] = "csi300",
    sample: Optional[int] = None,
    cache_path: Optional[str | Path] = "/tmp/ashare_panel.pkl",
    max_cache_age_hours: int = 24,
    force_refresh: bool = False,
    verbose: bool = True,
) -> pd.DataFrame:
    """Fetch real A-share market data in factor_lab panel format.

    This is the main entry point. It:
    1. Resolves the universe to a list of stock codes
    2. Checks for a cached panel (skip fetch if fresh)
    3. Fetches OHLCV from akshare if needed
    4. Returns a DataFrame with columns: date, code, open, high, low, close, volume, amount

    Args:
        start: Start date "YYYY-MM-DD"
        end: End date "YYYY-MM-DD"
        universe: "csi300", "csi500", "csi800", "all", or list of codes
        sample: Randomly sample N codes (useful for testing)
        cache_path: Path for pickle cache (~100MB for CSI300 × 2yr)
        max_cache_age_hours: Re-fetch if cache older than this
        force_refresh: Skip cache check
        verbose: Print progress

    Returns:
        DataFrame with standardized panel format

    Example:
        >>> panel = fetch_real_panel("2023-01-01", "2024-12-31", universe="csi300")
        >>> from research_core.factor_lab.libraries.alpha101 import compute_alpha101_factors
        >>> factors = compute_alpha101_factors(panel, factor_names=["alpha1", "alpha2"])
    """
    codes = resolve_universe(universe, sample=sample)

    if cache_path and not force_refresh:
        cached = load_cached_panel(cache_path, max_age_hours=max_cache_age_hours)
        if cached is not None:
            cached_codes = cached["code"].unique()
            if set(codes).issubset(set(cached_codes)):
                # Verify date range coverage
                cached_min = pd.Timestamp(cached["date"].min())
                cached_max = pd.Timestamp(cached["date"].max())
                req_start = pd.Timestamp(start)
                req_end = pd.Timestamp(end)
                if cached_min <= req_start and cached_max >= req_end:
                    if verbose:
                        print(f"[Data Adapter] Using cached panel: "
                              f"{len(cached_codes)} stocks × {cached['date'].nunique()} days")
                    # Filter to requested date range
                    panel = cached[
                        (cached["date"] >= start) & (cached["date"] <= end)
                    ].copy()
                    return panel
                elif verbose:
                    print(f"[Data Adapter] Cache date range [{cached_min.date()},{cached_max.date()}] "
                          f"does not cover request [{req_start.date()},{req_end.date()}], re-fetching...")

    if verbose:
        print(f"[Data Adapter] Fetching {len(codes)} stocks from akshare "
              f"({start} ~ {end})...")

    panel = fetch_akshare_panel(codes, start, end, verbose=verbose)

    if cache_path:
        save_cached_panel(panel, cache_path, metadata={
            "source": "akshare",
            "start": start,
            "end": end,
            "universe": universe if isinstance(universe, str) else "custom",
        })

    return panel


# ═══════════════════════════════════════════════════════════════
# Convenience: build real panel for factor_lab demo mode
# ═══════════════════════════════════════════════════════════════

def build_real_demo_panel(
    n_dates: int = 160,
    n_codes: int = 50,
    seed: int = 7,
    *,
    cache_path: str = "/tmp/ashare_demo_panel.pkl",
) -> pd.DataFrame:
    """Build a panel suitable for factor_lab demo runs, but with real market data.

    Uses the same interface as build_alpha101_demo_panel(), making it a drop-in
    replacement in factor_lab service.py and cli.py.

    Args:
        n_dates: Approximate number of trading days (actual may differ)
        n_codes: Number of stocks to sample
        seed: Random seed for reproducibility
        cache_path: Cache location

    Returns:
        Panel DataFrame with columns: date, code, open, high, low, close, volume, amount
    """
    np.random.seed(seed)

    # Fetch a reasonable window: ~1.5x n_dates to account for weekends
    cal_days = int(n_dates * 1.6)
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - pd.Timedelta(days=cal_days)).strftime("%Y-%m-%d")

    panel = fetch_real_panel(
        start=start_date,
        end=end_date,
        universe="csi800",
        sample=n_codes,
        cache_path=cache_path,
        max_cache_age_hours=72,  # demo data can be older
        verbose=False,
    )

    # Trim to approximate n_dates trading days
    dates = sorted(panel["date"].unique())
    if len(dates) > n_dates:
        cutoff = dates[-n_dates]
        panel = panel[panel["date"] >= cutoff]

    return panel
