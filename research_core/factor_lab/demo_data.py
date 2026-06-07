from __future__ import annotations

import numpy as np
import pandas as pd


def build_alpha101_demo_panel(
    *,
    n_dates: int = 160,
    n_codes: int = 8,
    seed: int = 7,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2021-01-01", periods=n_dates, freq="B")
    codes = [f"stock_{idx:03d}" for idx in range(1, n_codes + 1)]
    records: list[dict[str, object]] = []

    for code_idx, code in enumerate(codes):
        base_price = 12 + code_idx * 2.5
        close = base_price
        for date in dates:
            market_trend = 0.0006 * (code_idx + 1)
            shock = rng.normal(market_trend, 0.015)
            close = max(close * (1 + shock), 1.0)
            open_ = max(close * (1 + rng.normal(0, 0.004)), 0.5)
            high = max(open_, close) * (1 + abs(rng.normal(0, 0.007)))
            low = min(open_, close) * (1 - abs(rng.normal(0, 0.007)))
            volume = int(rng.integers(500_000, 5_000_000))
            amount = volume * (open_ + high + low + close) / 4
            records.append(
                {
                    "date": date,
                    "code": code,
                    "open": open_,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": volume,
                    "amount": amount,
                }
            )

    return pd.DataFrame(records)
