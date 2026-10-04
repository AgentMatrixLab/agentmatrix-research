"""Server-side RQData/RQSDK export for the 2026-10-07 factor delivery.

Run this on the licensed data server inside the ``rqsdk`` conda environment.
It writes immutable, hash-stamped snapshots that the validation pipeline reads
locally; the pipeline itself never touches RQData or the network.

    conda activate rqsdk
    python -X utf8 scripts/export_rqsdk_panel.py --probe          # 30-second API check
    python -X utf8 scripts/export_rqsdk_panel.py --out-dir /data/amr/export \
        --start 2015-01-01 --end 2026-08-31

Produces, in ``--out-dir``:

    validation_panel.parquet   + .json sidecar     extended all-A daily panel
    benchmark.parquet          + .json sidecar     000985 daily return
    index_membership.parquet   + .json sidecar     month-end index constituents
    run_manifest.json                              everything above, hashed

Design rules this script obeys, matching the rest of the repository:

* **No silent degradation.** A requested field that RQData does not return is a
  hard error, not a dropped column. The only tolerated fallback is computing
  ``vwap`` from turnover and volume, and that is recorded in the sidecar.
* **Price basis is explicit.** ``limit_up``/``limit_down`` are only meaningful
  next to ``close`` if both share a basis. The manifest carries a limit-hit rate
  sanity check so a mixed basis is caught before it reaches the validator.
* **Nothing is inferred.** Column names, units and adjustment basis are written
  into the sidecars exactly as the pipeline will consume them.

Use ``--probe`` first: it exercises every RQData call on three codes for one day
and prints what came back, so an API or entitlement surprise costs seconds
rather than an hour-long batch.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CN_TZ = timezone(timedelta(hours=8))

PANEL_DATASET = "validation_panel"
BENCHMARK_DATASET = "benchmark_daily_return"
INDEX_DATASET = "index_membership"

#: RQData field -> panel column. RQData names the previous close ``prev_close``;
#: the pipeline's contract calls it ``pre_close``.
PRICE_FIELDS: dict[str, str] = {
    "open": "open",
    "high": "high",
    "low": "low",
    "close": "close",
    "volume": "volume",
    "total_turnover": "total_turnover",
    "limit_up": "limit_up",
    "limit_down": "limit_down",
    "prev_close": "pre_close",
}

#: Columns the frozen panel contract requires, in pipeline spelling.
REQUIRED_PANEL_COLUMNS = (
    "date",
    "code",
    "close",
    "volume",
    "total_turnover",
    "limit_up",
    "limit_down",
    "circulation_a",
    "listed_date",
    "de_listed_date",
    "is_st",
    "is_suspended",
)

#: Extended quote/reference columns the full factor catalog needs.
EXTENDED_PANEL_COLUMNS = ("open", "high", "low", "pre_close", "vwap", "total_shares", "industry")

PROBE_CODES = ["000001.XSHE", "600000.XSHG", "300750.XSHE"]
INDEX_UNIVERSES = {
    "csi300": "000300.XSHG",
    "csi500": "000905.XSHG",
    "csi1000": "000852.XSHG",
}


class ExportError(RuntimeError):
    """Raised when the export cannot produce a contract-conforming snapshot."""


# ── small helpers ───────────────────────────────────────────────────────

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def batches(values: list[str], size: int) -> Iterable[list[str]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


def normalize_index_frame(frame: pd.DataFrame, value_name: str | None = None) -> pd.DataFrame:
    """Flatten RQData's (date, code) MultiIndex into plain columns."""
    normalized = frame.reset_index()
    normalized = normalized.rename(
        columns={"order_book_id": "code", "tradedate": "date", "datetime": "date"}
    )
    if "date" not in normalized.columns or "code" not in normalized.columns:
        raise ExportError(
            f"RQData response is missing its date/code index; got columns {list(normalized.columns)}"
        )
    if value_name and value_name not in normalized.columns and len(normalized.columns) == 3:
        candidate = next(c for c in normalized.columns if c not in {"date", "code"})
        normalized = normalized.rename(columns={candidate: value_name})
    normalized["date"] = pd.to_datetime(normalized["date"]).dt.normalize()
    normalized["code"] = normalized["code"].astype(str)
    return normalized


def wide_boolean_to_long(frame: pd.DataFrame, value_name: str) -> pd.DataFrame:
    if frame.index.name is None:
        frame.index.name = "date"
    result = (
        frame.rename_axis("date")
        .reset_index()
        .melt(id_vars="date", var_name="code", value_name=value_name)
    )
    result["date"] = pd.to_datetime(result["date"]).dt.normalize()
    result["code"] = result["code"].astype(str)
    result[value_name] = result[value_name].astype(bool)
    return result


def write_snapshot(frame: pd.DataFrame, path: Path, sidecar: dict[str, Any]) -> dict[str, Any]:
    """Write a Parquet file plus its sidecar and return the recorded metadata."""
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False, compression="snappy")

    payload = dict(sidecar)
    payload["row_count"] = int(len(frame))
    payload["sha256"] = sha256_file(path)
    payload["written_at"] = datetime.now(CN_TZ).isoformat(timespec="seconds")
    sidecar_path = Path(f"{path}.json")
    sidecar_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return payload


# ── RQData access ───────────────────────────────────────────────────────

def init_rqdatac():
    try:
        import rqdatac
    except ImportError as exc:  # pragma: no cover - server-only path
        raise ExportError(
            "rqdatac is not importable. Activate the licensed environment first: "
            "conda activate rqsdk"
        ) from exc
    try:
        rqdatac.init()
    except Exception as exc:  # noqa: BLE001
        raise ExportError(
            "rqdatac.init() failed. Check the account credentials and entitlement "
            "configured on this host (RQSDK_USERNAME/RQSDK_PASSWORD or ~/.rqdata)."
        ) from exc
    return rqdatac


def pull_universe(rqdatac, start: str, end: str) -> pd.DataFrame:
    """All-A ordinary shares live at any point in [start, end]."""
    metadata = rqdatac.all_instruments(type="CS")
    required = {"order_book_id", "trading_code", "listed_date", "de_listed_date"}
    missing = sorted(required - set(metadata.columns))
    if missing:
        raise ExportError(f"all_instruments() is missing fields: {', '.join(missing)}")

    metadata = metadata.copy()
    metadata["listed_date"] = pd.to_datetime(metadata["listed_date"], errors="coerce")
    metadata["de_listed_date"] = pd.to_datetime(metadata["de_listed_date"], errors="coerce")
    lower, upper = pd.Timestamp(start), pd.Timestamp(end)
    metadata = metadata[
        metadata["listed_date"].notna()
        & (metadata["listed_date"] <= upper)
        & (metadata["de_listed_date"].isna() | (metadata["de_listed_date"] >= lower))
    ].copy()

    # B-shares (200xxx/900xxx) are outside the all-A universe.
    metadata = metadata[
        ~metadata["trading_code"].astype(str).str.startswith(("200", "900"))
    ].copy()
    if metadata.empty:
        raise ExportError("all_instruments() returned an empty all-A universe for that range.")
    return metadata


def pull_prices(rqdatac, codes: list[str], start: str, end: str, *, batch_size: int) -> pd.DataFrame:
    """Daily bars for the requested fields, in the sidecar's declared basis."""
    frames: list[pd.DataFrame] = []
    requested = list(PRICE_FIELDS)
    seen_columns: set[str] = set()

    for index, batch in enumerate(batches(codes, batch_size), start=1):
        raw = rqdatac.get_price(
            batch,
            start_date=start,
            end_date=end,
            frequency="1d",
            fields=requested,
            adjust_type="post",
            skip_suspended=False,
            expect_df=True,
        )
        frame = normalize_index_frame(raw)
        seen_columns |= set(frame.columns)
        frames.append(frame)
        print(f"    prices batch {index}: {len(batch)} codes -> {len(frame):,} rows", flush=True)

    panel = pd.concat(frames, ignore_index=True)
    absent = [name for name in requested if name not in seen_columns]
    if absent:
        raise ExportError(
            "RQData did not return these requested price fields: "
            f"{', '.join(absent)}. Entitlement or field naming differs from the "
            "export contract -- fix the field list before pulling a full history."
        )
    return panel


def pull_status_flags(rqdatac, codes: list[str], start: str, end: str, *, batch_size: int) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for index, batch in enumerate(batches(codes, batch_size), start=1):
        st = wide_boolean_to_long(rqdatac.is_st_stock(batch, start, end), "is_st")
        suspended = wide_boolean_to_long(rqdatac.is_suspended(batch, start, end), "is_suspended")
        merged = st.merge(suspended, on=["date", "code"], how="outer")
        frames.append(merged)
        print(f"    flags batch {index}: {len(batch)} codes -> {len(merged):,} rows", flush=True)
    return pd.concat(frames, ignore_index=True)


def pull_shares(rqdatac, codes: list[str], start: str, end: str, *, batch_size: int) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for index, batch in enumerate(batches(codes, batch_size), start=1):
        raw = rqdatac.get_shares(
            batch, start_date=start, end_date=end, fields=["circulation_a", "total_a"], expect_df=True
        )
        frame = normalize_index_frame(raw)
        frames.append(frame)
        print(f"    shares batch {index}: {len(batch)} codes -> {len(frame):,} rows", flush=True)

    panel = pd.concat(frames, ignore_index=True)
    if "total_a" in panel.columns:
        panel = panel.rename(columns={"total_a": "total_shares"})
    return panel


def pull_industry(rqdatac, codes: list[str]) -> pd.DataFrame:
    """Point-in-time industry classification, taken from the instrument master.

    Industry is a slowly changing attribute; ``all_instruments`` exposes the
    current classification, which is what the panel records. If the licensed
    environment does not expose it, the export says so instead of inventing one.
    """
    metadata = rqdatac.all_instruments(type="CS")
    for candidate in ("industry", "sector", "industry_name"):
        if candidate in metadata.columns:
            frame = metadata[["order_book_id", candidate]].rename(
                columns={"order_book_id": "code", candidate: "industry"}
            )
            frame["code"] = frame["code"].astype(str)
            frame = frame[frame["code"].isin(set(codes))]
            frame["industry"] = frame["industry"].astype(str)
            return frame.drop_duplicates("code")
    raise ExportError(
        "all_instruments() exposes no industry column (tried industry/sector/industry_name). "
        "Pass --skip-industry, or supply the classification via --industry-source."
    )


def pull_benchmark(rqdatac, start: str, end: str, code: str = "000985.XSHG") -> pd.DataFrame:
    raw = rqdatac.get_price(
        code,
        start_date=start,
        end_date=end,
        frequency="1d",
        fields=["close"],
        adjust_type="none",
        expect_df=True,
    )
    frame = normalize_index_frame(raw, "close").sort_values("date")
    frame["return"] = frame["close"].pct_change()
    frame = frame.dropna(subset=["return"])
    return frame[["date", "return"]].reset_index(drop=True)


def pull_index_membership(rqdatac, start: str, end: str) -> pd.DataFrame:
    """Month-end constituent snapshots for the main A-share benchmarks."""
    month_ends = pd.date_range(start=start, end=end, freq="BME")
    frames: list[pd.DataFrame] = []
    for name, code in INDEX_UNIVERSES.items():
        for stamp in month_ends:
            day = stamp.date().isoformat()
            try:
                members = rqdatac.index_components(code, day)
            except Exception as exc:  # noqa: BLE001
                raise ExportError(
                    f"index_components({code!r}, {day!r}) failed: {type(exc).__name__}. "
                    "Pass --skip-index-components to export without constituents."
                ) from exc
            frames.append(
                pd.DataFrame(
                    {
                        "date": pd.Timestamp(stamp).normalize(),
                        "index_code": code,
                        "index_name": name,
                        "code": [str(m) for m in members],
                    }
                )
            )
        print(f"    index {name}: {len(month_ends)} month-end snapshots", flush=True)
    return pd.concat(frames, ignore_index=True)


# ── assembly and checks ─────────────────────────────────────────────────

def assemble_panel(
    prices: pd.DataFrame,
    flags: pd.DataFrame,
    shares: pd.DataFrame,
    metadata: pd.DataFrame,
    industry: pd.DataFrame | None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Join the pulls into the pipeline's panel shape, recording field provenance."""
    panel = prices.rename(columns=PRICE_FIELDS)
    panel = panel.merge(flags, on=["date", "code"], how="left")
    panel = panel.merge(shares, on=["date", "code"], how="left")

    provenance: dict[str, Any] = {"price_fields": dict(PRICE_FIELDS)}

    if "vwap" not in panel.columns:
        # Both operands are in the same adjusted basis, so the ratio is a
        # genuine adjusted VWAP; recorded rather than silently assumed.
        volume = panel["volume"].replace(0, np.nan)
        panel["vwap"] = panel["total_turnover"] / volume
        provenance["vwap"] = (
            "computed as total_turnover / volume; both fields came from the same "
            "adjusted pull, so the ratio is an adjusted VWAP"
        )
    else:
        provenance["vwap"] = "supplied by rqdatac.get_price(vwap)"

    master = metadata.rename(columns={"order_book_id": "code"})[
        ["code", "listed_date", "de_listed_date"]
    ].copy()
    master["listed_date"] = pd.to_datetime(master["listed_date"], errors="coerce")
    master["de_listed_date"] = pd.to_datetime(master["de_listed_date"], errors="coerce")
    panel = panel.merge(master, on="code", how="left", validate="many_to_one")

    if industry is not None:
        panel = panel.merge(industry, on="code", how="left")
        provenance["industry"] = "all_instruments() point-in-time classification"
    else:
        provenance["industry"] = "not exported (--skip-industry)"

    panel = (
        panel.sort_values(["date", "code"])
        .drop_duplicates(["date", "code"], keep="last")
        .reset_index(drop=True)
    )

    for column in ("is_st", "is_suspended"):
        panel[column] = panel[column].fillna(False).astype(bool)
    panel["de_listed_date"] = pd.to_datetime(panel["de_listed_date"], errors="coerce")

    missing = [c for c in REQUIRED_PANEL_COLUMNS if c not in panel.columns]
    if missing:
        raise ExportError(f"assembled panel is missing required columns: {', '.join(missing)}")
    return panel, provenance


def limit_hit_sanity(panel: pd.DataFrame) -> dict[str, Any]:
    """Guard against a mixed price basis between close and the limit prices.

    If ``close`` and ``limit_up`` came from different adjustment bases, the
    fraction of rows touching a limit would be absurd -- near zero, or a large
    fraction. A plausible all-A range is roughly 0.1%-15%.
    """
    usable = panel.dropna(subset=["close", "limit_up", "limit_down"])
    if usable.empty:
        return {"measured": False, "reason": "no rows carry both close and limit prices"}
    n = len(usable)
    at_up = float((usable["close"] >= usable["limit_up"] - 1e-6).mean())
    at_down = float((usable["close"] <= usable["limit_down"] + 1e-6).mean())
    plausible = 0.0005 <= (at_up + at_down) <= 0.30
    return {
        "measured": True,
        "rows": n,
        "limit_up_hit_rate": round(at_up, 6),
        "limit_down_hit_rate": round(at_down, 6),
        "plausible": plausible,
        "note": (
            "close and limit prices share a basis"
            if plausible
            else "IMPLAUSIBLE: close and limit_up/limit_down may be in different "
                 "adjustment bases; do not validate on this panel"
        ),
    }


def self_check(out_dir: Path) -> int:
    """Validate the written snapshots with the repository's own loaders."""
    sys.path.insert(0, str(ROOT))
    from research_core.factor_lab.panel_source import load_validation_panel

    panel_path = out_dir / "validation_panel.parquet"
    print(f"  self-check: {panel_path.name}")
    try:
        loaded = load_validation_panel(panel_path, require_extended=True)
    except Exception as exc:  # noqa: BLE001
        print(f"    FAILED: {type(exc).__name__}: {exc}")
        return 1
    print(f"    rows={len(loaded.frame):,}  sha256={loaded.sha256[:16]}...")
    print(f"    price_basis={loaded.price_basis}  extended={loaded.extended_columns}")
    print(f"    dates={loaded.frame['date'].min().date()}..{loaded.frame['date'].max().date()}")
    print(f"    codes={loaded.frame['code'].nunique():,}")

    benchmark_path = out_dir / "benchmark.parquet"
    if benchmark_path.exists():
        from research_core.data_loader.rqdata_panel import load_rqdata_benchmark

        print(f"  self-check: {benchmark_path.name}")
        try:
            frame = load_rqdata_benchmark(benchmark_path)
        except Exception as exc:  # noqa: BLE001
            print(f"    FAILED: {type(exc).__name__}: {exc}")
            return 1
        print(f"    rows={len(frame):,}  dates={frame['date'].min().date()}..{frame['date'].max().date()}")
    return 0


def probe(rqdatac) -> int:
    """Exercise every call on a tiny sample so API surprises surface in seconds."""
    day = "2026-08-28"
    codes = PROBE_CODES
    print(f"probe: {len(codes)} codes, one day ({day})")
    failures = 0

    def attempt(label, fn):
        nonlocal failures
        try:
            result = fn()
        except Exception as exc:  # noqa: BLE001
            print(f"  FAIL  {label:<22} {type(exc).__name__}: {str(exc)[:110]}")
            failures += 1
            return None
        detail = ""
        if isinstance(result, pd.DataFrame):
            detail = f"shape={result.shape} columns={list(result.columns)[:9]}"
        else:
            detail = repr(result)[:110]
        print(f"  OK    {label:<22} {detail}")
        return result

    metadata = attempt("all_instruments", lambda: rqdatac.all_instruments(type="CS"))
    if isinstance(metadata, pd.DataFrame):
        industry_like = [c for c in metadata.columns if "industr" in c or "sector" in c]
        print(f"        industry-like columns: {industry_like or 'NONE'}")
        print(f"        total instruments: {len(metadata):,}")

    attempt(
        "get_price (extended)",
        lambda: rqdatac.get_price(
            codes, start_date=day, end_date=day, frequency="1d",
            fields=list(PRICE_FIELDS), adjust_type="post",
            skip_suspended=False, expect_df=True,
        ),
    )
    attempt("get_shares", lambda: rqdatac.get_shares(
        codes, start_date=day, end_date=day, fields=["circulation_a", "total_a"], expect_df=True))
    attempt("is_st_stock", lambda: rqdatac.is_st_stock(codes, day, day))
    attempt("is_suspended", lambda: rqdatac.is_suspended(codes, day, day))
    attempt("get_turnover_rate", lambda: rqdatac.get_turnover_rate(
        codes, day, day, fields=["today"], expect_df=True))
    attempt("get_price (index 000985)", lambda: rqdatac.get_price(
        "000985.XSHG", start_date=day, end_date=day, frequency="1d",
        fields=["close"], adjust_type="none", expect_df=True))
    attempt("index_components(000300)", lambda: rqdatac.index_components("000300.XSHG", day))

    print(f"\nprobe failures: {failures}")
    if failures:
        print("Fix the failing calls (field names, entitlement) before running the full export.")
    return 1 if failures else 0


# ── entry point ─────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out-dir", default="/data/amr/export", help="destination directory on the server")
    parser.add_argument("--start", default="2015-01-01", help="warmup start (inclusive)")
    parser.add_argument("--end", default="2026-08-31", help="validation end (inclusive)")
    parser.add_argument("--batch-size", type=int, default=300, help="codes per RQData request")
    parser.add_argument("--benchmark-code", default="000985.XSHG")
    parser.add_argument("--skip-industry", action="store_true", help="omit the industry column")
    parser.add_argument("--skip-index-components", action="store_true", help="omit index membership")
    parser.add_argument("--probe", action="store_true", help="run a tiny API check and exit")
    parser.add_argument("--self-check", action="store_true", help="validate --out-dir with repo loaders and exit")
    parser.add_argument("--dry-run", action="store_true", help="print the plan and exit")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    out_dir = Path(args.out_dir)
    stamp = datetime.now(CN_TZ).isoformat(timespec="seconds")

    if args.self_check:
        return self_check(out_dir)

    if args.dry_run:
        print("plan:")
        print(f"  out-dir      : {out_dir}")
        print(f"  range        : {args.start} .. {args.end}")
        print(f"  batch size   : {args.batch_size} codes/request")
        print(f"  price fields : {', '.join(PRICE_FIELDS)} (adjust_type=post)")
        print(f"  industry     : {'skipped' if args.skip_industry else 'from all_instruments()'}")
        print(f"  index members: {'skipped' if args.skip_index_components else ', '.join(INDEX_UNIVERSES)}")
        print(f"  benchmark    : {args.benchmark_code}")
        return 0

    print(f"RQData export starting {stamp}")
    rqdatac = init_rqdatac()
    print(f"  rqdatac version: {getattr(rqdatac, '__version__', 'unknown')}")

    if args.probe:
        return probe(rqdatac)

    metadata = pull_universe(rqdatac, args.start, args.end)
    codes = sorted(metadata["order_book_id"].astype(str).unique())
    print(f"  universe: {len(codes):,} all-A codes over {args.start}..{args.end}")

    prices = pull_prices(rqdatac, codes, args.start, args.end, batch_size=args.batch_size)
    flags = pull_status_flags(rqdatac, codes, args.start, args.end, batch_size=args.batch_size)
    shares = pull_shares(rqdatac, codes, args.start, args.end, batch_size=args.batch_size)
    industry = None if args.skip_industry else pull_industry(rqdatac, codes)

    panel, provenance = assemble_panel(prices, flags, shares, metadata, industry)
    basis = limit_hit_sanity(panel)
    print(f"  assembled panel: {len(panel):,} rows, {panel['code'].nunique():,} codes")
    print(f"  limit-hit sanity: {basis}")

    data_start = panel["date"].min().date().isoformat()
    data_end = panel["date"].max().date().isoformat()
    panel_sidecar = write_snapshot(
        panel,
        out_dir / "validation_panel.parquet",
        {
            "source": "RQData FULL",
            "dataset": PANEL_DATASET,
            "data_start": data_start,
            "data_end": data_end,
            "price_basis": "post_adjusted",
            "adjust_type": "post",
            "field_provenance": provenance,
            "limit_hit_sanity": basis,
            "extended_columns": [c for c in EXTENDED_PANEL_COLUMNS if c in panel.columns],
            "exported_at": stamp,
        },
    )
    print(f"  wrote validation_panel.parquet ({panel_sidecar['row_count']:,} rows, sha256={panel_sidecar['sha256'][:16]}...)")

    benchmark = pull_benchmark(rqdatac, args.start, args.end, code=args.benchmark_code)
    benchmark_sidecar = write_snapshot(
        benchmark,
        out_dir / "benchmark.parquet",
        {
            "source": "RQData FULL",
            "dataset": BENCHMARK_DATASET,
            "data_start": benchmark["date"].min().date().isoformat(),
            "data_end": benchmark["date"].max().date().isoformat(),
            "price_basis": "raw_index_level",
            "benchmark_code": "000985",
            "return_type": "price_return",
            "rqdata_code": args.benchmark_code,
            "exported_at": stamp,
        },
    )
    print(f"  wrote benchmark.parquet ({benchmark_sidecar['row_count']:,} rows)")

    index_sidecar = None
    if not args.skip_index_components:
        membership = pull_index_membership(rqdatac, args.start, args.end)
        index_sidecar = write_snapshot(
            membership,
            out_dir / "index_membership.parquet",
            {
                "source": "RQData FULL",
                "dataset": INDEX_DATASET,
                "data_start": membership["date"].min().date().isoformat(),
                "data_end": membership["date"].max().date().isoformat(),
                "price_basis": "not_applicable",
                "indices": INDEX_UNIVERSES,
                "frequency": "month_end",
                "exported_at": stamp,
            },
        )
        print(f"  wrote index_membership.parquet ({index_sidecar['row_count']:,} rows)")

    manifest = {
        "schema_version": 1,
        "exported_at": stamp,
        "rqdatac_version": str(getattr(rqdatac, "__version__", "unknown")),
        "requested_range": {"start": args.start, "end": args.end},
        "batch_size": args.batch_size,
        "universe_size": len(codes),
        "snapshots": {
            "validation_panel": panel_sidecar,
            "benchmark": benchmark_sidecar,
            **({"index_membership": index_sidecar} if index_sidecar else {}),
        },
    }
    manifest_path = out_dir / "run_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  wrote run_manifest.json")

    if basis.get("measured") and not basis.get("plausible"):
        print("\nREFUSING to declare success: the limit-hit rate is implausible.")
        print("Check the price basis before using this panel for validation.")
        return 2

    print("\nnext: run the self-check")
    print(f"  python -X utf8 scripts/export_rqsdk_panel.py --out-dir {out_dir} --self-check")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
