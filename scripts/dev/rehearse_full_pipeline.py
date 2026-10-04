"""Rehearse the whole 10/07 delivery chain on synthetic data, end to end.

The pieces each pass their own tests, but that proves nothing about whether they
compose. The last integration bug found here -- the validator writing rank-IC
keys as ``"10d"`` while a consumer looked up ``"10"`` -- passed 53 tests and
would have reported "0 of 900 factors passed FDR" on the first real batch.

So this script runs the real chain, in order, against synthetic inputs:

    synthetic extended panel
      -> engine computes factor values from catalog expressions
        -> frozen `validate-batch` (all eight gates, unmodified)
          -> supplementary robustness layer (FDR + industry neutrality)
            -> scoring and correlation clustering
              -> strategy targets, order export, execution reconciliation

Every artefact is written under ``--work-dir`` (default ``.tmp-rehearsal``) and
is explicitly marked TEST_ONLY_SYNTHETIC. **This is not evidence about any
factor.** Its only job is to prove the machinery is wired together correctly
before real data lands.

The frozen config is never edited: the rehearsal writes a copy that differs from
`configs/validation_gates.yaml` in exactly one key, ``output.root``, and asserts
that is the only difference.

    python -X utf8 scripts/dev/rehearse_full_pipeline.py
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import export_rqsdk_panel as export  # noqa: E402
from research_core.factor_lab.catalog_readiness import classify_expression  # noqa: E402
from research_core.factor_lab.formula_compiler import UnsupportedOperatorError, compile_formula  # noqa: E402
from research_core.factor_lab.panel_source import load_validation_panel  # noqa: E402
from research_core.factor_lab.precomputed_factors import load_precomputed_factors  # noqa: E402
from research_core.factor_lab.scoring import cluster_factors, score_batch, select_representatives  # noqa: E402
from research_core.factor_lab.supplementary import build_supplementary_report  # noqa: E402
from research_core.strategy_operations.signal_pipeline import (  # noqa: E402
    build_targets,
    diff_positions,
    reconcile_execution,
    to_supabase_rows,
)

FROZEN_CONFIG = ROOT / "configs" / "validation_gates.yaml"
CATALOG = ROOT / "pages" / "factor-db-dashboard" / "data" / "factors.json"

#: Enough names per cross-section for the frozen `minimum_cross_section: 20`,
#: with room for the industry-neutralisation cells to stay rankable.
N_CODES = 60
N_INDUSTRIES = 6
START = "2015-01-05"
END = "2026-08-31"

#: Catalog expressions chosen for a rehearsal: every one is a plain rolling
#: statistic with a single integer window, so perturbed variants are mechanical.
CANDIDATE_EXPRESSIONS: list[tuple[str, str, int]] = [
    ("REH_ROC20", "Ref($close, 20)/$close", 20),
    ("REH_MA10", "Mean($close, 10)/$close", 10),
    ("REH_STD20", "Std($close, 20)/$close", 20),
    ("REH_RSV5", "($close-Min($low, 5))/(Max($high, 5)-Min($low, 5)+1e-12)", 5),
    ("REH_CORR20", "Corr($close, Log($volume+1), 20)", 20),
    ("REH_VMA10", "Mean($volume, 10)/($volume+1e-12)", 10),
    ("REH_BIAS6", "Bias($close, 6)", 6),
    ("REH_RSI14", "RSI($close, 14)", 14),
    ("REH_EMA12", "EMA($close, 12)/$close", 12),
    ("REH_QUANT20", "Quantile($close, 20, 0.8)/$close", 20),
]


# ── stage 1: synthetic inputs ───────────────────────────────────────────

def build_panel(seed: int) -> pd.DataFrame:
    """A synthetic extended panel with a real industry structure."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(START, END)
    industries = [f"IND{i:02d}" for i in range(N_INDUSTRIES)]
    frames = []

    for index in range(N_CODES):
        industry = industries[index % N_INDUSTRIES]
        # A slow common drift plus idiosyncratic noise, so cross-sectional
        # dispersion exists without any factor being genuinely predictive.
        drift = rng.normal(0.0002, 0.0001)
        shocks = rng.normal(drift, 0.021, len(dates))
        close = (8.0 + index * 0.9) * np.exp(np.cumsum(shocks))
        open_ = close * (1 + rng.normal(0, 0.005, len(dates)))
        high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0.007, 0.004, len(dates))))
        low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0.007, 0.004, len(dates))))
        volume = rng.lognormal(14.4, 0.45, len(dates))
        previous = np.concatenate([[close[0]], close[:-1]])

        frames.append(
            pd.DataFrame(
                {
                    "date": dates,
                    "code": f"{index:06d}.XSHE",
                    "open": open_,
                    "high": np.maximum.reduce([high, open_, close]),
                    "low": np.minimum.reduce([low, open_, close]),
                    "close": close,
                    "pre_close": previous,
                    "volume": volume,
                    "total_turnover": volume * close,
                    "vwap": close,
                    "limit_up": previous * 1.1,
                    "limit_down": previous * 0.9,
                    "circulation_a": 1.0e8 + index * 4.0e6,
                    "total_shares": 1.6e8 + index * 4.0e6,
                    "listed_date": pd.Timestamp("2010-01-04"),
                    "de_listed_date": pd.NaT,
                    "is_st": False,
                    "is_suspended": False,
                    "industry": industry,
                }
            )
        )

    panel = pd.concat(frames, ignore_index=True)
    # A handful of limit events so the export's mixed-basis guard has something
    # real to measure rather than tripping on a zero rate.
    for code_index in range(N_CODES):
        mask = panel["code"] == f"{code_index:06d}.XSHE"
        positions = panel.index[mask][:: max(len(dates) // 40, 1)]
        panel.loc[positions, "close"] = panel.loc[positions, "limit_up"]
    return panel.sort_values(["date", "code"]).reset_index(drop=True)


def write_panel(panel: pd.DataFrame, work_dir: Path) -> Path:
    path = work_dir / "validation_panel.parquet"
    export.write_snapshot(
        panel,
        path,
        {
            "source": "TEST_ONLY_SYNTHETIC",
            "dataset": export.PANEL_DATASET,
            "data_start": panel["date"].min().date().isoformat(),
            "data_end": panel["date"].max().date().isoformat(),
            "price_basis": "post_adjusted",
            "adjust_type": "post",
            "field_provenance": {"note": "SYNTHETIC rehearsal data. Not factor evidence."},
            "limit_hit_sanity": export.limit_hit_sanity(panel),
        },
    )
    return path


# ── stage 2: factor values from the engine ──────────────────────────────

def compute_factors(panel: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Compile each candidate expression and evaluate it on the panel.

    Also injects planted fixtures. Running the gates only over noise proves they
    run, not that they discriminate -- everything failing looks the same whether
    the gates work or are simply broken shut. A fixture with a genuine (and
    deliberately look-ahead) relationship to the forward return must PASS, and
    the noise factors must mostly FAIL. Only then does the rehearsal say
    anything about the gates themselves.
    """
    rows: list[pd.DataFrame] = []
    declared: dict[str, dict[str, int]] = {}
    computed: list[str] = []
    skipped: list[dict[str, str]] = []

    for factor_id, expression, window in CANDIDATE_EXPRESSIONS:
        readiness = classify_expression(expression)
        if not readiness.runnable:
            skipped.append({"factor_id": factor_id, "reason": f"not runnable: {readiness.verdict}"})
            continue

        try:
            function = compile_formula(expression)
        except UnsupportedOperatorError as exc:
            skipped.append({"factor_id": factor_id, "reason": str(exc)})
            continue

        try:
            values = pd.Series(function(panel))
        except Exception as exc:  # noqa: BLE001
            skipped.append({"factor_id": factor_id, "reason": f"{type(exc).__name__}: {exc}"})
            continue

        base = pd.DataFrame(
            {"date": panel["date"], "code": panel["code"], "factor_name": factor_id, "value": values}
        )
        rows.append(base)

        # Perturbed parameterisations, so `parameter_perturbation` is actually
        # measurable rather than auto-failing as "unmeasured".
        for multiplier in (0.8, 1.2):
            perturbed_window = max(int(round(window * multiplier)), 2)
            perturbed_expression = _substitute_window(expression, window, perturbed_window)
            if perturbed_expression == expression:
                continue
            try:
                perturbed = pd.Series(compile_formula(perturbed_expression)(panel))
            except Exception:  # noqa: BLE001
                continue
            rows.append(
                pd.DataFrame(
                    {
                        "date": panel["date"],
                        "code": panel["code"],
                        "factor_name": f"{factor_id}|window={perturbed_window}",
                        "value": perturbed,
                    }
                )
            )
        declared[factor_id] = {"window": int(window)}
        computed.append(factor_id)

    planted_rows, planted_ids = _planted_fixtures(panel)
    for factor_id in planted_ids:
        declared[factor_id] = {"window": 10}
    rows.extend(planted_rows)
    computed.extend(planted_ids)

    if not rows:
        raise SystemExit("no candidate expression could be computed; nothing to rehearse")

    table = pd.concat(rows, ignore_index=True)
    table = table.replace([np.inf, -np.inf], np.nan)
    return table, {
        "declared": declared,
        "computed": computed,
        "skipped": skipped,
        "planted": planted_ids,
    }


def _planted_fixtures(panel: pd.DataFrame) -> tuple[list[pd.DataFrame], list[str]]:
    """Fixtures that DO predict the synthetic forward return, by construction.

    ``PLANTED_LOOKAHEAD`` is the future 10-day return plus a little noise, so a
    working pipeline must pass it. It is deliberately look-ahead and must never
    be a real factor; it exists so that "nothing passed" cannot be mistaken for
    "the gates work".
    """
    ordered = panel.sort_values(["code", "date"]).reset_index(drop=True)
    close = ordered.groupby("code", sort=False)["close"]
    forward = close.shift(-10) / ordered["close"] - 1.0
    rng = np.random.default_rng(99)

    rows: list[pd.DataFrame] = []
    for factor_id, series, window in (
        ("PLANTED_LOOKAHEAD", forward, 10),
        ("PLANTED_WEAK", forward * 0.35 + pd.Series(rng.normal(0, 0.02, len(ordered))), 10),
    ):
        rows.append(
            pd.DataFrame(
                {
                    "date": ordered["date"],
                    "code": ordered["code"],
                    "factor_name": factor_id,
                    "value": pd.Series(series).to_numpy(),
                }
            )
        )
        # Perturbed variants so `parameter_perturbation` is measurable.
        for perturbed_window in (8, 12):
            perturbed_forward = close.shift(-perturbed_window) / ordered["close"] - 1.0
            rows.append(
                pd.DataFrame(
                    {
                        "date": ordered["date"],
                        "code": ordered["code"],
                        "factor_name": f"{factor_id}|window={perturbed_window}",
                        "value": pd.Series(perturbed_forward).to_numpy(),
                    }
                )
            )
    return rows, ["PLANTED_LOOKAHEAD", "PLANTED_WEAK"]


def _substitute_window(expression: str, old: int, new: int) -> str:
    """Replace the single integer literal that equals ``old``."""
    import re

    replaced = re.sub(rf"(?<![0-9.]){old}(?![0-9.])", str(new), expression, count=1)
    return replaced


def write_factor_table(table: pd.DataFrame, declared: dict, work_dir: Path) -> Path:
    path = work_dir / "factor_values.parquet"
    table.to_parquet(path, index=False)
    metadata = {
        "source": "TEST_ONLY_SYNTHETIC",
        "dataset": "factor_values",
        "data_start": table["date"].min().date().isoformat(),
        "data_end": table["date"].max().date().isoformat(),
        "row_count": int(len(table)),
        "sha256": export.sha256_file(path),
        "factors": declared,
        "value_definition": (
            "SYNTHETIC rehearsal factor values produced by the repository expression "
            "engine on synthetic prices. Not factor evidence."
        ),
    }
    Path(f"{path}.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return path


def write_candidate_list(computed: list[str], work_dir: Path) -> Path:
    path = work_dir / "candidate_list.csv"
    frame = pd.DataFrame(
        {
            "factor_id": computed,
            "risk_exposure": ["false"] * len(computed),
            "window": [dict(CANDIDATE_EXPRESSIONS_BY_ID)[f] for f in computed],
        }
    )
    frame.to_csv(path, index=False, encoding="utf-8")
    return path


CANDIDATE_EXPRESSIONS_BY_ID = {
    factor_id: window for factor_id, _expression, window in CANDIDATE_EXPRESSIONS
} | {factor_id: 10 for factor_id in ("PLANTED_LOOKAHEAD", "PLANTED_WEAK")}


# ── stage 3: the frozen pipeline ────────────────────────────────────────

def write_rehearsal_config(work_dir: Path) -> Path:
    """Copy the frozen config, changing only ``output.root``.

    Redirecting the output keeps rehearsal artefacts away from the real
    ``data/factor_lab/validation_runs``. The assertion below is the guarantee
    that no gate value, split or cost assumption moves with it.
    """
    frozen = yaml.safe_load(FROZEN_CONFIG.read_text(encoding="utf-8"))
    rehearsal = json.loads(json.dumps(frozen))  # deep copy through JSON
    rehearsal["output"]["root"] = str(work_dir / "validation_runs")

    # Prove the only difference really is the output root.
    restored = json.loads(json.dumps(rehearsal))
    restored["output"]["root"] = frozen["output"]["root"]
    if restored != frozen:
        raise SystemExit(
            "rehearsal config differs from the frozen config in more than output.root"
        )

    path = work_dir / "rehearsal_config.yaml"
    path.write_text(yaml.safe_dump(rehearsal, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def run(command: list[str]) -> int:
    print(f"  $ {' '.join(command)}", flush=True)
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    tail = (completed.stdout or "").strip().splitlines()[-6:]
    for line in tail:
        print(f"    {line}")
    if completed.returncode != 0:
        for line in (completed.stderr or "").strip().splitlines()[-14:]:
            print(f"    ! {line}")
    return completed.returncode


# ── orchestration ───────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", default=".tmp-rehearsal")
    parser.add_argument("--seed", type=int, default=20261005)
    parser.add_argument("--keep", action="store_true", help="keep the work directory on success")
    args = parser.parse_args(argv)

    work_dir = ROOT / args.work_dir
    shutil.rmtree(work_dir, ignore_errors=True)
    work_dir.mkdir(parents=True, exist_ok=True)

    failures: list[str] = []

    def step(label: str) -> None:
        print(f"\n=== {label} ===", flush=True)

    step("1/7 synthetic extended panel")
    panel = build_panel(args.seed)
    panel_path = write_panel(panel, work_dir)
    loaded = load_validation_panel(panel_path, require_extended=True)
    print(f"  rows={len(loaded.frame):,} codes={loaded.frame['code'].nunique()}")
    print(f"  extended columns: {loaded.extended_columns}")

    step("2/7 engine computes factor values")
    table, meta = compute_factors(panel)
    print(f"  computed {len(meta['computed'])} factor(s), skipped {len(meta['skipped'])}")
    for item in meta["skipped"]:
        print(f"    skipped {item['factor_id']}: {item['reason'][:90]}")
    if not meta["computed"]:
        return 1
    factor_path = write_factor_table(table, meta["declared"], work_dir)
    load_precomputed_factors(factor_path)  # contract must accept what we wrote
    print(f"  factor table rows={len(table):,} (base + perturbation variants)")

    step("3/7 candidate list")
    candidates = write_candidate_list(meta["computed"], work_dir)
    print(f"  {candidates.name}: {len(meta['computed'])} factors")

    step("4/7 frozen validate-batch (all eight gates)")
    config_path = write_rehearsal_config(work_dir)
    code = run(
        [
            sys.executable, "-X", "utf8", "-m", "research_core.factor_lab.cli", "validate-batch",
            "--candidates", str(candidates),
            "--config", str(config_path),
            "--panel-file", str(panel_path),
            "--factor-file", str(factor_path),
            "--segment", "oos",
            "--output-dir", str(work_dir / "batch"),
        ]
    )
    if code != 0:
        failures.append(f"validate-batch exited {code}")

    runs_dir = work_dir / "validation_runs"
    results = sorted(runs_dir.glob("*/validation_result.json")) if runs_dir.exists() else []
    print(f"  produced {len(results)} validation_result.json")
    if not results:
        failures.append("the frozen validator produced no results")

    validated = 0
    passed_ids: list[str] = []
    failed_ids: list[str] = []
    for path in results:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("failed_gates"):
            failed_ids.append(payload["factor_id"])
        else:
            validated += 1
            passed_ids.append(payload["factor_id"])
    print(f"  passed every gate: {validated}/{len(results)}")
    print(f"    passed: {sorted(passed_ids)}")
    print(f"    failed: {sorted(failed_ids)}")

    # The gates must DISCRIMINATE, not merely run. A pipeline that rejects
    # everything looks identical to a pipeline that is broken shut.
    if "PLANTED_LOOKAHEAD" not in passed_ids:
        detail = ""
        for path in results:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload["factor_id"] == "PLANTED_LOOKAHEAD":
                detail = ", ".join(payload.get("failed_gates") or [])
        failures.append(
            f"PLANTED_LOOKAHEAD failed the gates ({detail or 'no result'}); the gates "
            "may be rejecting everything rather than discriminating"
        )
    if validated >= len(results):
        failures.append(
            "every factor passed, including the pure-noise ones; the gates are not "
            "rejecting anything and cannot be discriminating"
        )

    if results:
        first = json.loads(results[0].read_text(encoding="utf-8"))
        keys = sorted((first.get("rank_ic") or {}).keys())
        print(f"  rank_ic key shape from the validator: {keys}")

    step("5/7 supplementary layer (FDR + industry neutrality)")
    payloads = [json.loads(path.read_text(encoding="utf-8")) for path in results]
    neutral = {}
    from research_core.factor_lab.supplementary import industry_neutral_retention

    panel_with_returns = loaded.frame.sort_values(["code", "date"]).reset_index(drop=True)
    grouped = panel_with_returns.groupby("code", sort=False)["close"]
    panel_with_returns["forward_return"] = grouped.shift(-10) / panel_with_returns["close"] - 1.0

    for payload in payloads:
        factor_id = payload["factor_id"]
        subset = table[(table["factor_name"] == factor_id)]
        if subset.empty:
            neutral[factor_id] = None
            continue
        keys = panel_with_returns[["date", "code"]].reset_index().rename(columns={"index": "_row"})
        merged = keys.merge(subset[["date", "code", "value"]], on=["date", "code"], how="left")
        series = merged.sort_values("_row")["value"].reset_index(drop=True)
        series.index = panel_with_returns.index
        neutral[factor_id] = industry_neutral_retention(
            panel_with_returns,
            factor_values=series,
            factor_col="_factor",
            return_col="forward_return",
        )

    report = build_supplementary_report(payloads, q=0.05, neutral_ic=neutral)
    summary = report["summary"]
    print(f"  submitted={summary['n_submitted']} testable={summary['n_tested']} "
          f"pass_fdr={summary['n_accepted']}")
    if summary["n_submitted"] and summary["n_tested"] == 0:
        failures.append(
            "the supplementary layer tested ZERO factors: the rank_ic key shape regression"
        )
    computed_neutral = sum(1 for value in neutral.values() if value)
    print(f"  industry-neutral retention computed for {computed_neutral}/{len(payloads)}")

    step("6/7 scoring and correlation clustering")
    batch = score_batch(payloads)
    print(f"  scored={batch['n_scored']} skipped={batch['n_skipped']} tiers={batch['tier_counts']}")
    if batch["n_skipped"]:
        for item in batch["skipped"][:3]:
            print(f"    skipped {item['factor_id']}: {item['reason'][:90]}")

    if batch["n_scored"] >= 2:
        wide = (
            table[~table["factor_name"].str.contains(r"\|window=", regex=True)]
            .pivot_table(index=["date", "code"], columns="factor_name", values="value")
        )
        # Cluster on the cross-sectional rank correlation, averaged over dates.
        ranks = wide.groupby(level="date").rank(pct=True)
        correlation = ranks.corr(method="spearman", min_periods=20)
        clusters = cluster_factors(correlation, threshold=0.7)
        scores = {item["factor_id"]: item for item in batch["factors"]}
        representatives = select_representatives(clusters["clusters"], scores)
        print(f"  clusters={clusters['n_clusters']} representatives={len(representatives)}")
    else:
        failures.append("fewer than two scored factors; clustering not exercised")

    step("7/7 strategy targets, signals and reconciliation")
    # A strategy scores STOCKS, not factors. Composite the passing factors into a
    # per-stock cross-sectional rank and trade the top of it.
    tradeable = [factor_id for factor_id in passed_ids if not factor_id.startswith("PLANTED_")]
    print(f"  factors usable in a strategy (planted fixtures excluded): {tradeable}")

    if tradeable and batch["n_scored"]:
        latest = panel_with_returns["date"].max()
        snapshot = panel_with_returns[panel_with_returns["date"] == latest].set_index("code")
        prices = {str(code): float(close) for code, close in snapshot["close"].items()}

        ranks = {}
        for factor_id in tradeable:
            subset = table[(table["factor_name"] == factor_id) & (table["date"] == latest)]
            if subset.empty:
                continue
            column = subset.set_index("code")["value"]
            ranks[factor_id] = column.rank(pct=True)
        if ranks:
            composite = pd.DataFrame(ranks).mean(axis=1).dropna()
            stock_scores = {str(code): float(value) for code, value in composite.items()}
            targets = build_targets(
                stock_scores, total_value=5e7, prices=prices, top_n=3,
                max_weight=0.5, weighting="score",
            )
            orders = diff_positions(targets, {}, total_value=5e7)
            rows = to_supabase_rows(
                orders, strategy_id="rehearsal", trade_date=latest.date().isoformat(),
                portfolio_value=5e7,
            )
            print(f"  targets={len(targets)} orders={len(orders)} supabase_rows={len(rows)}")

            fills = pd.DataFrame(
                [
                    {"code": order.code, "side": order.side, "shares": order.shares,
                     "price": order.reference_price}
                    for order in orders[:-1]
                ]
                or [{"code": "none", "side": "buy", "shares": 0, "price": 1.0}]
            )
            reconciliation = reconcile_execution(
                orders, fills, trade_date=latest.date().isoformat(), strategy_id="rehearsal"
            )
            print(f"  reconciliation clean={reconciliation.is_clean} "
                  f"missing={len(reconciliation.missing)} ratio={reconciliation.fill_ratio:.3f}")
            if len(orders) > 1 and reconciliation.is_clean:
                failures.append("reconciliation called a deliberately incomplete fill set clean")
        else:
            failures.append("passing factors produced no usable stock scores")
    else:
        failures.append(
            "no non-planted factor passed, so the strategy and signal stages were not exercised"
        )

    report_path = work_dir / "rehearsal_report.json"
    report_path.write_text(
        json.dumps(
            {
                "n_codes": int(panel["code"].nunique()),
                "n_factors_computed": len(meta["computed"]),
                "n_skipped": len(meta["skipped"]),
                "n_validation_results": len(results),
                "n_validated": validated,
                "n_scored": batch["n_scored"],
                "tier_counts": batch["tier_counts"],
                "failure_reasons": failures,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("\n" + "=" * 64)
    if failures:
        print("REHEARSAL FAILED")
        for item in failures:
            print(f"  - {item}")
    else:
        print("REHEARSAL PASSED: panel -> engine -> frozen gates -> FDR -> score -> signals")

    if not args.keep and not failures:
        shutil.rmtree(work_dir, ignore_errors=True)
    else:
        print(f"artefacts kept in {work_dir}")
    print("SYNTHETIC DATA ONLY -- this run is not evidence about any factor.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
