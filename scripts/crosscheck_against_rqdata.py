"""Cross-validate our engine against RQData's independent implementation.

Where our catalog and RQData's factor library cover the same indicator, the two
should agree. They were written by different people from the same 通达信-style
definitions, so agreement is genuine external evidence about our engine rather
than another round of our own tests passing.

The expected failure mode is not "our maths is wrong" but a definitional gap --
adjustment basis, window length, or smoothing. So the report gives a per-variant
correlation and names the best-matching parameterisation rather than a bare pass or
fail, because "ATR matched at 14, not at 10" is the useful statement.

    python -X utf8 scripts/crosscheck_against_rqdata.py --output crosscheck.json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CLICKHOUSE = "/usr/local/bin/clickhouse-client"
CH_USER = "smartdata_ro"
CH_PASSWORD_ENV = "CH_PASSWORD"

#: Indicators present in both libraries, mapped to our catalog prefixes.
#: Derived by scripts/dev/find_crosscheck_overlap.py against the live catalog.
CROSSCHECK_MAP: dict[str, str] = {
    "ADX": "TDXGS_ADX", "ADXR": "TDXGS_ADXR", "AR": "TDXGS_AR",
    "ATR": "TDXGS_ATR", "BBI": "TDXGS_BBI", "BIAS": "TDXGS_BIAS",
    "CCI": "TDXGS_CCI", "CR": "TDXGS_CR", "DPO": "TDXGS_DPO",
    "EMV": "TDXGS_EMV", "MFI": "TDXGS_MFI", "MTM": "TDXGS_MTM",
    "OBV": "TDXGS_OBV", "PSY": "TDXGS_PSY", "ROC": "TDXGS_ROC",
    "RSI": "TDXGS_RSI", "TRIX": "TDXGS_TRIX", "VR": "TDXGS_VR",
    "WR": "TDXGS_WR",
}

#: A rank correlation at or above this is treated as the same indicator.
AGREEMENT_THRESHOLD = 0.95
#: Below this the two are not describing the same thing at all.
DIVERGENCE_THRESHOLD = 0.50


def rqdata_factor(name: str, start: str, end: str) -> pd.DataFrame:
    """One RQData factor's daily values, straight from ClickHouse as Parquet."""
    password = __import__("os").environ.get(CH_PASSWORD_ENV, "")
    if not password:
        raise SystemExit(f"set {CH_PASSWORD_ENV} before running")
    sql = (
        "SELECT toString(trade_date) AS date, order_book_id AS code, "
        "toFloat64(factor_value) AS value "
        "FROM rqdata.stock_factor_daily_long "
        f"WHERE factor_name = '{name}' AND trade_date >= '{start}' AND trade_date <= '{end}' "
        "FORMAT Parquet"
    )
    completed = subprocess.run(
        [CLICKHOUSE, "--user", CH_USER, "--password", password, "--query", sql],
        capture_output=True,
    )
    if completed.returncode != 0:
        raise SystemExit(f"clickhouse query failed for {name}: {completed.stderr.decode()[:300]}")
    import io

    frame = pd.read_parquet(io.BytesIO(completed.stdout))
    frame["date"] = pd.to_datetime(frame["date"])
    return frame


def per_date_rank_correlation(ours: pd.Series, theirs: pd.Series, min_cross: int = 30) -> dict:
    """Average cross-sectional Spearman IC between the two series.

    Computed per date and averaged, not pooled: pooling would let a common time
    trend manufacture agreement between two series that disagree in every
    cross-section, which is the only place a factor is used.
    """
    joined = pd.concat([ours.rename("ours"), theirs.rename("theirs")], axis=1).dropna()
    if joined.empty:
        return {"n_dates": 0, "n_obs": 0, "mean_ic": float("nan"), "median_ic": float("nan")}

    correlations: list[float] = []
    for _, group in joined.groupby(level="date", sort=True):
        if len(group) < min_cross:
            continue
        if group["ours"].nunique() < 2 or group["theirs"].nunique() < 2:
            continue
        value = group["ours"].corr(group["theirs"], method="spearman")
        if np.isfinite(value):
            correlations.append(float(value))

    if not correlations:
        return {"n_dates": 0, "n_obs": int(len(joined)), "mean_ic": float("nan"), "median_ic": float("nan")}
    return {
        "n_dates": len(correlations),
        "n_obs": int(len(joined)),
        "mean_ic": float(np.mean(correlations)),
        "median_ic": float(np.median(correlations)),
        "share_above_0_9": float(np.mean(np.array(correlations) > 0.9)),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--factor-file", required=True, help="our factor_values.parquet")
    parser.add_argument("--start", default="2023-01-01")
    parser.add_argument("--end", default="2026-08-31")
    parser.add_argument("--output", default="crosscheck_rqdata.json")
    args = parser.parse_args(argv)

    from research_core.factor_lab.precomputed_factors import load_precomputed_factors

    ours_all = load_precomputed_factors(args.factor_file)
    available = [name for name in ours_all.factor_names if "|window=" not in name]
    print(f"our factor file: {len(available)} base series")
    print(f"window: {args.start} .. {args.end}\n")

    results: list[dict] = []
    for rq_name, prefix in CROSSCHECK_MAP.items():
        variants = [name for name in available if name.split(":")[-1].startswith(prefix)]
        if not variants:
            print(f"  {rq_name:<8} SKIP (no local variant)")
            continue
        try:
            theirs_frame = rqdata_factor(rq_name, args.start, args.end)
        except SystemExit as exc:
            print(f"  {rq_name:<8} SKIP ({exc})")
            continue
        theirs = theirs_frame.set_index(["date", "code"])["value"].sort_index()
        print(f"  {rq_name:<8} RQData rows={len(theirs):,}  our variants={len(variants)}")

        best: dict | None = None
        for name in variants:
            ours = ours_all.series[name].sort_index()
            stats = per_date_rank_correlation(ours, theirs)
            entry = {"our_factor": name, "rqdata_factor": rq_name, **stats}
            results.append(entry)
            if best is None or (stats["mean_ic"] or -1) > (best["mean_ic"] or -1):
                best = entry
        if best:
            verdict = (
                "AGREE" if best["mean_ic"] >= AGREEMENT_THRESHOLD
                else "CHECK" if best["mean_ic"] >= DIVERGENCE_THRESHOLD
                else "DIVERGE"
            )
            print(f"           best={best['our_factor']} ic={best['mean_ic']:.4f} "
                  f"dates={best['n_dates']} -> {verdict}")
            best["verdict"] = verdict

    Path(args.output).write_text(
        json.dumps({"window": [args.start, args.end], "results": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"\nwrote {args.output}")
    if results:
        best_by_indicator: dict[str, dict] = {}
        for entry in results:
            current = best_by_indicator.get(entry["rqdata_factor"])
            if current is None or (entry["mean_ic"] or -1) > (current["mean_ic"] or -1):
                best_by_indicator[entry["rqdata_factor"]] = entry
        agreed = [k for k, v in best_by_indicator.items() if (v["mean_ic"] or 0) >= AGREEMENT_THRESHOLD]
        diverged = [k for k, v in best_by_indicator.items() if (v["mean_ic"] or 0) < DIVERGENCE_THRESHOLD]
        print(f"  indicators checked : {len(best_by_indicator)}")
        print(f"  agree (ic >= {AGREEMENT_THRESHOLD}) : {len(agreed)}  {sorted(agreed)}")
        print(f"  diverge (ic <  {DIVERGENCE_THRESHOLD}) : {len(diverged)}  {sorted(diverged)}")
        print("\n  A divergence is a definitional question (adjustment basis, window, smoothing),")
        print("  not automatically our error -- but it must be explained before delivery.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
