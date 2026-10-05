"""Build the validation panel in the engine's contract, on the 115 server.

Takes the existing `/home/data/delivery_export/rqdata_panel.parquet` -- raw OHLC
plus an adjustment factor -- and produces a `validation_panel` that
`research_core.factor_lab.panel_source` accepts, with the extended columns the
catalog needs.

Decisions worth stating, because each one changes factor values:

* **Adjusted prices.** The source stores unadjusted OHLC and a separate
  `adjustment_factor` (= post-adjusted close / raw close). Price-based factors are
  only comparable across time once adjusted, so open/high/low/close/pre_close/vwap
  and the limit prices are all multiplied by it. `total_turnover` is a cash amount
  and is left unadjusted -- that is what `advN` means.
* **Warm-up history.** The frozen train window starts 2020-01-02, but a 252-bar
  window needs a year of history before it, so the panel starts 2018-01-01. The
  validator slices to the split itself; extra history is for warm-up only.
* **Industry** comes from the citics_2019 snapshots and is forward-filled, since
  they are only half-yearly.

    python -X utf8 scripts/prepare_server_panel.py \
        --source /home/data/delivery_export/rqdata_panel.parquet \
        --output /home/data/agentmatrix_run/panel/validation_panel.parquet
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

CN_TZ = timezone(timedelta(hours=8))

CLICKHOUSE = "/usr/local/bin/clickhouse-client"
CH_USER = "smartdata_ro"
CH_PASSWORD = "<redacted>"

SHARES_SQL = """
SELECT order_book_id AS code,
       toString(trade_date) AS date,
       toFloat64(circulation_a) AS circulation_a,
       toFloat64(total) AS total_shares
FROM rqdata.stock_shares
WHERE trade_date >= '2019-12-01'
FORMAT Parquet
"""

INDUSTRY_SQL = """
SELECT order_book_id AS code,
       toString(query_date) AS query_date,
       toString(first_industry_name) AS industry
FROM rqdata.stock_industry_snapshot
WHERE industry_source = 'citics_2019'
  AND first_industry_name IS NOT NULL
  AND first_industry_name != ''
ORDER BY query_date
FORMAT Parquet
"""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def clickhouse_parquet(sql: str, target: Path) -> pd.DataFrame:
    """Pull a query straight to Parquet and read it back."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as handle:
        completed = subprocess.run(
            [CLICKHOUSE, "--user", CH_USER, "--password", CH_PASSWORD, "--query", sql],
            stdout=handle, stderr=subprocess.PIPE,
        )
    if completed.returncode != 0:
        raise SystemExit(f"clickhouse query failed: {completed.stderr.decode()[:400]}")
    return pd.read_parquet(target)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", default="/home/data/delivery_export/rqdata_panel.parquet")
    parser.add_argument("--output", default="/home/data/agentmatrix_run/panel/validation_panel.parquet")
    parser.add_argument("--start", default="2018-01-01", help="warm-up start")
    parser.add_argument("--end", default="2026-08-31")
    parser.add_argument("--work-dir", default="/home/data/agentmatrix_run/ref")
    args = parser.parse_args(argv)

    work = Path(args.work_dir)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    print("=== 1/5 read source panel ===")
    frame = pd.read_parquet(args.source)
    print(f"  {len(frame):,} rows, columns={list(frame.columns)}")

    print("\n=== 2/5 rename to the engine contract ===")
    frame = frame.rename(columns={
        "amount": "total_turnover",
        "listing_date": "listed_date",
        "delisting_date": "de_listed_date",
    })
    frame["date"] = pd.to_datetime(frame["date"])
    frame["code"] = frame["code"].astype(str)
    frame = frame[(frame["date"] >= args.start) & (frame["date"] <= args.end)].copy()
    print(f"  {len(frame):,} rows after slicing {args.start} .. {args.end}")

    print("\n=== 3/5 adjust prices ===")
    if "adjustment_factor" not in frame.columns:
        raise SystemExit("source has no adjustment_factor column; refusing to guess a basis")
    adjust = pd.to_numeric(frame["adjustment_factor"], errors="coerce")
    print(f"  adjustment_factor: min={adjust.min():.4f} median={adjust.median():.4f} max={adjust.max():.4f} "
          f"null={int(adjust.isna().sum())}")
    if (adjust <= 0).any():
        raise SystemExit("adjustment_factor has non-positive values; refusing to apply it")
    frame = frame.sort_values(["code", "date"], kind="stable").reset_index(drop=True)
    adjust = pd.to_numeric(frame["adjustment_factor"], errors="coerce")

    for column in ("open", "high", "low", "close", "limit_up", "limit_down"):
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce") * adjust

    # vwap: cash / shares is the raw traded price; adjust it like any other price.
    volume = pd.to_numeric(frame["volume"], errors="coerce")
    turnover = pd.to_numeric(frame["total_turnover"], errors="coerce")
    vwap = (turnover / volume.replace(0, np.nan)) * adjust
    if "vwap" in frame.columns:
        # Prefer a vendor vwap where it exists, adjusted; fall back to the ratio.
        vendor = pd.to_numeric(frame["vwap"], errors="coerce") * adjust
        frame["vwap"] = vendor.where(vendor.notna(), vwap)
    else:
        frame["vwap"] = vwap
    print(f"  vwap from turnover/volume: {int(frame['vwap'].notna().sum()):,} non-null")

    # pre_close: previous adjusted close within each code.
    frame["pre_close"] = frame.groupby("code")["close"].shift(1)

    print("\n=== 4/5 reference data from ClickHouse ===")
    shares = clickhouse_parquet(SHARES_SQL, work / "stock_shares.parquet")
    shares["date"] = pd.to_datetime(shares["date"])
    shares["code"] = shares["code"].astype(str)
    print(f"  shares: {len(shares):,} rows, {shares['code'].nunique():,} codes, "
          f"{shares['date'].min().date()} .. {shares['date'].max().date()}")
    frame = frame.merge(shares, on=["code", "date"], how="left")

    # Share counts only start 2020-01-02, while the panel starts 2018-01-01 for
    # warm-up. Carry each code's earliest known count backwards and the latest
    # forwards: share counts move slowly, and circulation_a only feeds a handful
    # of turnover-ratio factors. Recorded in the sidecar rather than assumed.
    for column in ("circulation_a", "total_shares"):
        frame[column] = (
            frame.groupby("code")[column]
            .transform(lambda s: s.ffill().bfill())
        )
    missing_shares = int(frame["circulation_a"].isna().sum())
    backfilled = int((frame["date"] < "2020-01-02").sum())
    print(f"  circulation_a null after fill: {missing_shares:,} "
          f"(rows before 2020-01-02 carried by fill: {backfilled:,})")

    industry = clickhouse_parquet(INDUSTRY_SQL, work / "industry.parquet")
    industry["query_date"] = pd.to_datetime(industry["query_date"])
    print(f"  industry: {len(industry):,} rows, {industry['code'].nunique():,} codes, "
          f"{industry['query_date'].nunique()} snapshots")
    # Half-yearly snapshots, so carry each forward to the next one.
    industry = industry.sort_values(["query_date", "code"])
    frame = pd.merge_asof(
        frame.sort_values("date"),
        industry.rename(columns={"query_date": "date"}).sort_values("date"),
        on="date", by="code", direction="backward",
    )
    coverage = frame["industry"].notna().mean()
    print(f"  industry coverage after forward-fill: {coverage:.1%}")

    print("\n=== 5/5 write ===")
    frame["is_st"] = frame["is_st"].fillna(False).astype(bool)
    frame["is_suspended"] = frame["is_suspended"].fillna(False).astype(bool)
    for column in ("listed_date", "de_listed_date"):
        frame[column] = pd.to_datetime(frame[column], errors="coerce")

    ordered = [
        "date", "code", "open", "high", "low", "close", "pre_close", "vwap",
        "volume", "total_turnover", "limit_up", "limit_down",
        "circulation_a", "total_shares", "is_st", "is_suspended",
        "listed_date", "de_listed_date", "industry", "adjustment_factor",
    ]
    frame = frame[[c for c in ordered if c in frame.columns]]
    frame = frame.sort_values(["date", "code"], kind="stable").reset_index(drop=True)

    if output.exists():
        output.unlink()
    frame.to_parquet(output, index=False)
    digest = sha256_file(output)

    sidecar = {
        "source": "RQData via ClickHouse rqdata.stock_price_1d_raw + stock_shares + stock_industry_snapshot",
        "dataset": "validation_panel",
        "data_start": str(frame["date"].min().date()),
        "data_end": str(frame["date"].max().date()),
        "row_count": int(len(frame)),
        "sha256": digest,
        "price_basis": "post_adjusted_ohlc_via_adjustment_factor; total_turnover unadjusted cash amount",
        "universe": f"{frame['code'].nunique()} codes",
        "industry_source": "citics_2019 (first level), forward-filled from half-yearly snapshots",
        "shares_note": (
            "circulation_a/total_shares come from rqdata.stock_shares, which starts 2020-01-02. "
            "Rows before that (warm-up only) carry the earliest known count per code via "
            "forward/backward fill."
        ),
        "generated_at": datetime.now(CN_TZ).isoformat(timespec="seconds"),
        "columns": list(frame.columns),
    }
    Path(f"{output}.json").write_text(
        json.dumps(sidecar, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"  wrote {output}")
    print(f"    rows       : {len(frame):,}")
    print(f"    codes      : {frame['code'].nunique():,}")
    print(f"    dates      : {frame['date'].min().date()} .. {frame['date'].max().date()}")
    print(f"    sha256     : {digest[:16]}...")
    print(f"    columns    : {list(frame.columns)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
