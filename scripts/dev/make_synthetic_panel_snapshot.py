"""Write a clearly-labelled SYNTHETIC panel snapshot for pre-flight rehearsal.

Purpose: rehearse the export -> self-check -> validation path *before* the real
RQData pull is available, so that when data lands the only unknown left is the
data itself.

The output is explicitly marked ``TEST_ONLY_SYNTHETIC`` in its sidecar and uses
shapes that no real market data would have. It must never be used as factor
evidence; the validation pipeline records the sidecar's ``source`` verbatim in
its run manifest precisely so this cannot be mistaken for RQData output.

    python -X utf8 scripts/dev/make_synthetic_panel_snapshot.py --out-dir .tmp-rehearsal
    python -X utf8 scripts/export_rqsdk_panel.py --out-dir .tmp-rehearsal --self-check
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import export_rqsdk_panel as export  # noqa: E402

CODES = [
    "000001.XSHE", "000002.XSHE", "600000.XSHG", "600519.XSHG",
    "300750.XSHE", "002594.XSHE", "601318.XSHG", "000858.XSHE",
]
INDUSTRIES = ["bank", "realestate", "bank", "consumer", "battery", "auto", "insurance", "consumer"]


def synthetic_panel(start: str, end: str, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start, end)
    frames = []

    for index, code in enumerate(CODES):
        shocks = rng.normal(0.0003, 0.022, len(dates))
        close = (10.0 + index * 3.0) * np.exp(np.cumsum(shocks))
        high = close * (1 + np.abs(rng.normal(0.008, 0.005, len(dates))))
        low = close * (1 - np.abs(rng.normal(0.008, 0.005, len(dates))))
        open_ = close * (1 + rng.normal(0, 0.005, len(dates)))
        volume = rng.lognormal(14.5, 0.45, len(dates))

        frame = pd.DataFrame(
            {
                "date": dates,
                "code": code,
                "open": np.minimum(open_, high),
                "high": np.maximum.reduce([high, open_, close]),
                "low": np.minimum.reduce([low, open_, close]),
                "close": close,
                "pre_close": np.concatenate([[close[0]], close[:-1]]),
                "volume": volume,
                "total_turnover": volume * close,
                "limit_up": np.concatenate([[close[0]], close[:-1]]) * 1.1,
                "limit_down": np.concatenate([[close[0]], close[:-1]]) * 0.9,
                "circulation_a": 1.0e8 + index * 1.0e7,
                "total_shares": 1.5e8 + index * 1.0e7,
                "listed_date": pd.Timestamp("2010-01-04"),
                "de_listed_date": pd.NaT,
                "is_st": False,
                "is_suspended": False,
                "industry": INDUSTRIES[index],
            }
        )

        # Guarantee a handful of limit events so the mixed-basis guard has
        # something real to measure against.
        for row in (5, 40, 90):
            if row < len(frame):
                frame.loc[row, "close"] = frame.loc[row, "limit_up"]
        frames.append(frame)

    panel = pd.concat(frames, ignore_index=True)
    # VWAP belongs next to the prices, not derived here, so the export's own
    # fallback path is what gets rehearsed.
    panel["vwap"] = panel["total_turnover"] / panel["volume"].replace(0, np.nan)
    return panel.sort_values(["date", "code"]).reset_index(drop=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default=".tmp-rehearsal")
    parser.add_argument("--start", default="2015-01-05")
    parser.add_argument("--end", default="2026-08-31")
    parser.add_argument("--seed", type=int, default=20261005)
    args = parser.parse_args(argv)

    out_dir = Path(args.out_dir)
    panel = synthetic_panel(args.start, args.end, args.seed)
    basis = export.limit_hit_sanity(panel)

    metadata = export.write_snapshot(
        panel,
        out_dir / "validation_panel.parquet",
        {
            "source": "TEST_ONLY_SYNTHETIC",
            "dataset": export.PANEL_DATASET,
            "data_start": panel["date"].min().date().isoformat(),
            "data_end": panel["date"].max().date().isoformat(),
            "price_basis": "post_adjusted",
            "adjust_type": "post",
            "field_provenance": {
                "note": "SYNTHETIC rehearsal data. Not RQData output. Not factor evidence."
            },
            "limit_hit_sanity": basis,
            "extended_columns": [c for c in export.EXTENDED_PANEL_COLUMNS if c in panel.columns],
        },
    )

    print(f"wrote {out_dir / 'validation_panel.parquet'}")
    print(f"  rows   : {metadata['row_count']:,}")
    print(f"  codes  : {panel['code'].nunique()}")
    print(f"  range  : {metadata['data_start']} .. {metadata['data_end']}")
    print(f"  sha256 : {metadata['sha256'][:16]}...")
    print(f"  limit-hit sanity: {basis}")
    print("\nSYNTHETIC DATA -- rehearsal only, never factor evidence.")
    print("next:")
    print(f"  python -X utf8 scripts/export_rqsdk_panel.py --out-dir {out_dir} --self-check")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
