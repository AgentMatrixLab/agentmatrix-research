"""Produce the client-facing delivery manifest from the pipeline's artifacts.

Joins the candidate list, the frozen-gate verdicts, the robustness layer, the
scoring card and the redundancy clustering into one frozen-schema CSV, plus a
summary of what is actually being delivered.

    python -X utf8 scripts/build_delivery_manifest.py \
        --candidates data/factor_lab/candidate_list.csv \
        --batch-manifest data/factor_lab/batches/merged/batch_manifest.json \
        --runs-dir data/factor_lab/validation_runs \
        --supplementary data/factor_lab/supplementary_report.json \
        --factor-file data/factor_lab/factors.parquet \
        --out data/factor_lab/delivery_manifest.csv

Scoring and clustering are computed here from the validation results rather than
read from a separate file, so there is one fewer artifact that can go stale
relative to the others.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research_core.factor_lab.delivery_manifest import (  # noqa: E402
    build_delivery_manifest,
    summarise_manifest,
    write_delivery_manifest,
)
from research_core.factor_lab.factor_catalog import build_factor_catalog  # noqa: E402
from research_core.factor_lab.scoring import (  # noqa: E402
    cluster_factors,
    score_batch,
    select_representatives,
)
from research_core.factor_lab.streaming_supplement import (  # noqa: E402
    cross_sectional_correlation,
)

CN_TZ = timezone(timedelta(hours=8))


def load_runs(runs_dir: Path) -> list[dict]:
    results = []
    for path in sorted(runs_dir.glob("*/validation_result.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload.setdefault("factor_id", path.parent.name)
        results.append(payload)
    return results


def compute_clusters(factor_file: Path, factor_ids: list[str], threshold: float) -> tuple[dict, list]:
    """Redundancy clusters from a bounded-memory correlation matrix.

    This used to pivot the whole long table into a dense ``(date, code) x factor`` frame and
    run Spearman on it. At the delivery scale that pivot is ~28 GB and pandas then needs
    further full-size copies inside ``rank`` and ``corr``, so it cannot run at all.
    `cross_sectional_correlation` streams each factor into one column of a float32 block and
    accumulates per-date statistics, which is the same statistic at a fraction of the memory.

    The matrix handed to `cluster_factors` is the daily cross-sectional Spearman averaged
    over dates, which is what `docs/delivery/methodology.md` specifies; the previous pooled
    figure is printed alongside so the substitution is visible in the run log.
    """
    if len(factor_ids) < 2:
        return {"n_clusters": 0, "clusters": []}, []

    print(f"  computing cross-sectional correlation for {len(factor_ids)} factor(s)")
    result = cross_sectional_correlation(factor_file, factor_ids=factor_ids)
    if result.correlation.empty or result.n_rows == 0:
        print("  no factor series were found; clustering is skipped")
        return {"n_clusters": 0, "clusters": []}, []
    if result.factors_missing:
        print(
            f"  WARNING: {len(result.factors_missing)} factor(s) have no series and are not "
            f"clustered: {result.factors_missing[:5]}"
        )
    print(
        f"  correlation: {result.n_rows:,} rows, {result.dates_used} date(s) used, "
        f"{result.dates_skipped} skipped; "
        f"max |daily-average - pooled| = {result.max_pooled_difference:.4f}"
    )

    available = [factor_id for factor_id in factor_ids if factor_id not in set(result.factors_missing)]
    matrix = result.correlation.loc[available, available]
    clusters = cluster_factors(matrix, threshold=threshold)
    return clusters, []  # representatives are chosen below once scores exist


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--candidates", required=True)
    parser.add_argument("--out", required=True)
    # These two are independent, not alternatives: the batch manifest is the
    # verdict source for the catalog, while the runs directory is what scoring and
    # clustering read. Requiring exactly one of them made the normal case -- both --
    # impossible.
    parser.add_argument("--batch-manifest", default="", help="batch_manifest.json, for catalog verdicts")
    parser.add_argument("--runs-dir", default="", help="per-factor runs, for scoring and clustering")
    parser.add_argument("--supplementary", default="", help="supplementary_report.json")
    parser.add_argument("--factor-file", default="", help="enables clustering")
    parser.add_argument("--cluster-threshold", type=float, default=0.7)
    parser.add_argument("--summary-out", default="", help="where the JSON summary goes")
    args = parser.parse_args(argv)

    if not args.batch_manifest and not args.runs_dir:
        parser.error("at least one of --batch-manifest or --runs-dir is required")

    catalog = build_factor_catalog(
        args.candidates,
        batch_manifest=args.batch_manifest or None,
        results_root=None if args.batch_manifest else (args.runs_dir or None),
    )
    print(f"catalog rows: {len(catalog)}")

    scoring: dict | None = None
    clusters: dict | None = None
    representatives: list = []
    runs: list[dict] = []

    if args.runs_dir:
        runs = load_runs(Path(args.runs_dir))
        print(f"validation results: {len(runs)}")
        if runs:
            scoring = score_batch(runs)
            print(f"scored {scoring['n_scored']} (skipped {scoring['n_skipped']}), tiers={scoring['tier_counts']}")

    if args.factor_file and scoring:
        scored_ids = [item["factor_id"] for item in scoring["factors"]]
        clusters, _ = compute_clusters(Path(args.factor_file), scored_ids, args.cluster_threshold)
        if clusters["clusters"]:
            scores_by_id = {item["factor_id"]: item for item in scoring["factors"]}
            representatives = select_representatives(clusters["clusters"], scores_by_id)
            print(f"clusters={clusters['n_clusters']}, representatives={len(representatives)}")

    supplementary = None
    if args.supplementary:
        supplementary = json.loads(Path(args.supplementary).read_text(encoding="utf-8"))
        print(f"supplementary: {supplementary.get('summary', {})}")

    rows = build_delivery_manifest(
        catalog,
        scoring=scoring,
        supplementary=supplementary,
        clusters=None if clusters is None else clusters.get("clusters"),
        representatives=representatives,
    )
    path = write_delivery_manifest(rows, args.out)
    summary = summarise_manifest(rows)
    summary["generated_at"] = datetime.now(CN_TZ).isoformat(timespec="seconds")
    summary["manifest_path"] = str(path)

    summary_path = Path(args.summary_out) if args.summary_out else path.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nwrote {path}")
    print(f"wrote {summary_path}")
    print(f"  validated            : {summary['validated']}")
    print(f"  rejected             : {summary['rejected']}")
    print(f"  not_run              : {summary['not_run']}")
    print(f"  tiers                : {summary['tier_counts']}")
    print(f"  pass FDR             : {summary['fdr_accepted']}")
    print(f"  IN DELIVERY PACKAGE  : {summary['in_delivery_package']}")
    print(f"  delivered clusters   : {summary['delivered_clusters']}")
    print(f"  representatives      : {summary['representatives']}")
    if summary["in_delivery_package"] == 0:
        print(
            "\nnote: nothing entered the package. That is the correct outcome when no "
            "factor cleared every frozen gate -- do not widen the gates to change it."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
