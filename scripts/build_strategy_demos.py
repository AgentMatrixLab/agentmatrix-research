"""Build the demo strategy set and their out-of-sample results.

Composes the pieces built for this delivery into the artefacts the client reads:
validated + scored factors -> several strategy variants -> target weights ->
a costed backtest -> NAV curves, metrics and IC -> the strategy dashboard's
`strategies.json` / `backtest_results.json`.

Four variants are built from the same passing factors, because a single strategy
proves nothing about whether the *selection* mattered:

    top_composite   every passing factor, weighted by cross-sectional rank
    cluster_core    only the correlation-cluster representatives
    single_best     the single highest-scoring factor
    all_passers     every passing factor, equal weight

Two guards matter more than the numbers:

* **Synthetic input cannot reach the client dashboard.** A `TEST_ONLY_SYNTHETIC`
  panel aborts the run unless ``--allow-synthetic`` is passed, and even then the
  output must go somewhere other than the published data directory.
* **A strategy is only reported if its factors cleared the frozen gates.** The
  runner reads validation results, not raw expression output, so a strategy can
  never be composed from factors that were rejected.

    python -X utf8 scripts/build_strategy_demos.py \
        --panel-file data/factor_lab/panel.parquet \
        --factor-file data/factor_lab/factors.parquet \
        --runs-dir data/factor_lab/validation_runs \
        --out-dir data/factor_lab/strategy_demos
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research_core.factor_lab.scoring import (  # noqa: E402
    cluster_factors,
    score_batch,
    select_representatives,
)
from research_core.strategy_operations.strategy_backtest import (  # noqa: E402
    DEFAULT_ROUND_TRIP_COST,
    backtest_weights,
    summarise_curve,
)

CN_TZ = timezone(timedelta(hours=8))
PUBLISHED_DIR = ROOT / "pages" / "strategy-dashboard" / "data"


class DemoError(RuntimeError):
    """Raised when the demo set cannot be built honestly."""


def read_sidecar(path: Path) -> dict:
    sidecar = Path(f"{path}.json")
    if not sidecar.is_file():
        raise DemoError(f"sidecar not found for {path}")
    return json.loads(sidecar.read_text(encoding="utf-8"))


def load_runs(runs_dir: Path) -> list[dict]:
    results = []
    for path in sorted(runs_dir.glob("*/validation_result.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload.setdefault("factor_id", path.parent.name)
        results.append(payload)
    if not results:
        raise DemoError(f"no validation results under {runs_dir}")
    return results


def composite_stock_scores(
    values: pd.DataFrame,
    factor_ids: list[str],
    weights: dict[str, float] | None = None,
) -> pd.DataFrame:
    """Average cross-sectional rank of the selected factors, per (date, code)."""
    selected = values[values["factor_name"].isin(factor_ids)]
    if selected.empty:
        raise DemoError("none of the selected factors has any values in the table")
    wide = selected.pivot_table(index=["date", "code"], columns="factor_name", values="value")
    ranks = wide.groupby(level="date").rank(pct=True)
    if weights:
        columns = [c for c in ranks.columns if c in weights]
        if columns:
            weights_series = pd.Series({c: weights[c] for c in columns})
            ranks = ranks[columns].mul(weights_series, axis=1)
    return ranks.mean(axis=1).rename("score").reset_index()


def month_end_dates(dates: pd.Series, *, count: int | None = None) -> list[pd.Timestamp]:
    unique = pd.DatetimeIndex(sorted(pd.to_datetime(dates).unique()))
    frame = pd.DataFrame(index=unique)
    ends = frame.groupby([unique.year, unique.month]).apply(lambda g: g.index.max())
    ordered = sorted(pd.Timestamp(value) for value in ends)
    return ordered[-count:] if count else ordered


def build_weights_for_dates(
    scores: pd.DataFrame,
    rebalance_dates: list[pd.Timestamp],
    *,
    top_n: int,
    max_weight: float,
) -> pd.DataFrame:
    """Equal-weight the top-N ranked names at each rebalance date."""
    rows: list[dict] = []
    for date in rebalance_dates:
        snapshot = scores[scores["date"] == date]
        if snapshot.empty:
            continue
        ranked = snapshot.sort_values("score", ascending=False).head(top_n)
        if ranked.empty:
            continue
        weight = min(1.0 / len(ranked), max_weight)
        for code in ranked["code"]:
            rows.append({"date": date, "code": str(code), "weight": weight})
    if not rows:
        raise DemoError("no target weights could be produced")
    return pd.DataFrame(rows)


VARIANTS = {
    "top_composite": "全部过闸因子按横截面排名加权",
    "cluster_core": "仅用相关性簇代表（低相关核心集）",
    "single_best": "仅用综合分最高的单因子",
    "all_passers": "全部过闸因子等权",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--panel-file", required=True)
    parser.add_argument("--factor-file", required=True)
    parser.add_argument("--runs-dir", required=True)
    parser.add_argument("--out-dir", default="data/factor_lab/strategy_demos")
    parser.add_argument("--top-n", type=int, default=50)
    parser.add_argument("--max-weight", type=float, default=0.05)
    parser.add_argument("--rebalances", type=int, default=36, help="how many month-ends to trade")
    parser.add_argument("--cluster-threshold", type=float, default=0.7)
    parser.add_argument("--round-trip-cost", type=float, default=DEFAULT_ROUND_TRIP_COST)
    parser.add_argument(
        "--allow-synthetic",
        action="store_true",
        help="permit TEST_ONLY_SYNTHETIC inputs; the output then may not go to the published dashboard",
    )
    args = parser.parse_args(argv)

    panel_path = Path(args.panel_file)
    factor_path = Path(args.factor_file)
    runs_dir = Path(args.runs_dir)
    out_dir = Path(args.out_dir)

    panel_sidecar = read_sidecar(panel_path)
    factor_sidecar = read_sidecar(factor_path)
    synthetic = "SYNTHETIC" in str(panel_sidecar.get("source", "")).upper()
    if synthetic and not args.allow_synthetic:
        raise SystemExit(
            "panel sidecar declares TEST_ONLY_SYNTHETIC. Synthetic results must never be "
            "presented as strategy evidence; pass --allow-synthetic for a rehearsal."
        )
    if synthetic and out_dir.resolve() == PUBLISHED_DIR.resolve():
        raise SystemExit(
            "refusing to write synthetic strategy results into the published dashboard directory"
        )

    panel = pd.read_parquet(panel_path)
    values = pd.read_parquet(factor_path)
    results = load_runs(runs_dir)

    passing = [item for item in results if not item.get("failed_gates")]
    print(f"validation results: {len(results)}, passing every frozen gate: {len(passing)}")
    if not passing:
        raise SystemExit(
            "no factor passed every frozen gate, so there is no strategy to build. "
            "This is a correct outcome on data with no signal."
        )

    batch = score_batch(results)
    scores_by_factor = {item["factor_id"]: item for item in batch["factors"]}
    ranked_factors = [item["factor_id"] for item in batch["factors"]]
    print(f"scored {batch['n_scored']} factor(s); tiers={batch['tier_counts']}")

    base = values[~values["factor_name"].str.contains(r"\|window=", regex=True)]
    available = [factor_id for factor_id in ranked_factors if factor_id in set(base["factor_name"])]
    if not available:
        raise SystemExit("none of the scored factors has base values in the factor table")

    # Cluster the passers so a low-correlation core can be carved out.
    wide = base[base["factor_name"].isin(available)].pivot_table(
        index=["date", "code"], columns="factor_name", values="value"
    )
    representatives: list[str] = []
    clusters: dict = {"n_clusters": 0, "clusters": []}
    if len(available) >= 2:
        ranks = wide.groupby(level="date").rank(pct=True)
        correlation = ranks.corr(method="spearman", min_periods=20)
        clusters = cluster_factors(correlation, threshold=args.cluster_threshold)
        reps = select_representatives(clusters["clusters"], scores_by_factor)
        representatives = [item["representative"] for item in reps]
        print(f"clusters={clusters['n_clusters']}, representatives={len(representatives)}")

    variants: dict[str, list[str]] = {
        "top_composite": available,
        "all_passers": available,
        "single_best": available[:1],
        "cluster_core": representatives or available,
    }

    rebalance_dates = month_end_dates(panel["date"], count=args.rebalances)
    benchmark_level = None
    benchmark_series = None
    if "industry" in panel.columns and {"date", "close"} <= set(panel.columns):
        market = panel.groupby("date")["close"].mean()
        benchmark_series = market
        benchmark_level = float(market.iloc[0])

    strategy_index: list[dict] = []
    backtest_results: dict[str, dict] = {}
    generated = datetime.now(CN_TZ).isoformat(timespec="seconds")

    for name, factor_ids in variants.items():
        if not factor_ids:
            continue
        stock_scores = composite_stock_scores(
            base, factor_ids, weights=None if name == "all_passers" else
            {fid: scores_by_factor[fid]["composite"] for fid in factor_ids}
        )
        try:
            weights = build_weights_for_dates(
                stock_scores, rebalance_dates, top_n=args.top_n, max_weight=args.max_weight
            )
        except DemoError as exc:
            print(f"  {name}: skipped ({exc})")
            continue

        try:
            backtest = backtest_weights(
                weights,
                panel[["date", "code", "close"]],
                round_trip_cost=args.round_trip_cost,
                benchmark=benchmark_series,
                benchmark_level=benchmark_level,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"  {name}: backtest failed ({type(exc).__name__}: {exc})")
            continue

        metrics = summarise_curve(backtest["curve"])
        strategy_id = f"delivery_{name}_v1"
        strategy_index.append(
            {
                "strategy_id": strategy_id,
                "name": VARIANTS.get(name, name),
                "status": "review_needed",
                "factor_ids": factor_ids,
                "n_factors": len(factor_ids),
                "top_n": args.top_n,
                "rebalances": backtest["metrics"]["rebalances"],
                "mean_traded_fraction": backtest["metrics"]["mean_traded_fraction"],
            }
        )
        backtest_results[strategy_id] = {
            "strategy_id": strategy_id,
            "nav": [point["nav"] for point in backtest["curve"]],
            "dates": [point["date"] for point in backtest["curve"]],
            "metrics": metrics,
            "turnover_basis": backtest["turnover_basis"],
            "factor_ids": factor_ids,
        }
        print(
            f"  {name}: {len(factor_ids)} factor(s), rebalances={backtest['metrics']['rebalances']}, "
            f"total_return={metrics.get('total_return'):.4f}, maxdd={metrics.get('max_drawdown'):.4f}"
        )

    if not backtest_results:
        raise SystemExit("no strategy variant could be built")

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "strategies.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": generated,
                "data_status": "synthetic_rehearsal" if synthetic else "real_run",
                "strategies": strategy_index,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (out_dir / "backtest_results.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": generated,
                "method": "month_end_rebalance_topN_equal_weight",
                "backtest_window": {
                    "start": backtest_results[next(iter(backtest_results))]["dates"][0],
                    "end": backtest_results[next(iter(backtest_results))]["dates"][-1],
                },
                "cost_model": {"round_trip_total": args.round_trip_cost},
                "universe_rule": f"all-A panel, top {args.top_n} by composite rank",
                "top_n": args.top_n,
                "clusters": clusters,
                "results": backtest_results,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"\nwrote {out_dir / 'strategies.json'}")
    print(f"wrote {out_dir / 'backtest_results.json'}")
    print(f"data_status = {'synthetic_rehearsal' if synthetic else 'real_run'}")
    if synthetic:
        print("\nSYNTHETIC REHEARSAL: these numbers are not strategy evidence.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
