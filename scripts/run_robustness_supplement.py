"""Run the supplementary robustness layer over a batch of validation results.

This is a **post-processing** step. It reads what the frozen validator produced
and adds two pieces of evidence the frozen gates cannot express:

1. **Benjamini-Hochberg FDR control** across the whole candidate batch. The
   frozen ``rank_ic`` gate tests each factor at |t| >= 1.65 in isolation; run that
   over ~900 factors and roughly one in twenty survivors is noise. FDR control is
   inherently a batch statistic, which is why it lives here and not in the gates.

2. **Industry-neutral IC retention**, when a panel is supplied. The frozen
   ``style_r2`` gate residualises on size/momentum/volatility/liquidity but has no
   industry term.

Nothing here writes to ``validation_result.json`` and nothing here can admit a
factor the frozen gates rejected: the report marks factors that clear FDR, and
the delivery rule is "frozen gates AND FDR", never "either".

    python -X utf8 scripts/run_robustness_supplement.py \
        --runs-dir data/factor_lab/validation_runs \
        --out data/factor_lab/supplementary_report.json --q 0.05

    # add industry-neutral retention (needs the panel and a factor-value table)
    python -X utf8 scripts/run_robustness_supplement.py \
        --runs-dir data/factor_lab/validation_runs \
        --panel-file data/factor_lab/panel.parquet \
        --factor-file data/factor_lab/factors.parquet \
        --out data/factor_lab/supplementary_report.json
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

from research_core.factor_lab.streaming_supplement import (  # noqa: E402
    neutral_retention_by_factor,
)
from research_core.factor_lab.supplementary import (  # noqa: E402
    build_supplementary_report,
    render_markdown,
)

CN_TZ = timezone(timedelta(hours=8))


def load_results(runs_dir: Path, only: list[str] | None = None) -> list[dict]:
    """Read every validation_result.json under ``runs_dir``."""
    if not runs_dir.exists():
        raise SystemExit(f"runs directory does not exist: {runs_dir}")

    wanted = set(only) if only else None
    results: list[dict] = []
    for result_path in sorted(runs_dir.glob("*/validation_result.json")):
        factor_id = result_path.parent.name
        if wanted is not None and factor_id not in wanted:
            continue
        try:
            payload = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"  skipping {result_path}: {type(exc).__name__}")
            continue
        payload.setdefault("factor_id", factor_id)
        results.append(payload)

    if not results:
        raise SystemExit(
            f"no validation_result.json found under {runs_dir}. "
            "Run the frozen validator first."
        )
    return results


def compute_neutral_ic(
    results: list[dict],
    panel_path: Path,
    factor_path: Path,
    *,
    horizon: int,
    neutralize_returns: bool,
    jobs: int = 1,
) -> dict:
    """Industry-neutral retention per factor, without loading the whole factor table.

    This used to ``pd.read_parquet`` the entire long table and then filter it once per
    factor. That is a full scan per factor -- ~450 scans of a table that reaches ten billion
    rows at the delivery scale -- and the initial load alone needs more memory than the box
    has. `neutral_retention_by_factor` streams one factor's series at a time instead, and
    aligns each to the panel by ``(date, code)`` exactly as before, so the numbers are
    unchanged.
    """
    factor_ids = [str(result["factor_id"]) for result in results]
    print(f"  streaming {len(factor_ids)} factor(s) from {factor_path} with jobs={jobs}")
    return neutral_retention_by_factor(
        factor_path,
        panel_path=panel_path,
        horizon=horizon,
        neutralize_returns=neutralize_returns,
        factor_ids=factor_ids,
        allow_missing=True,
        progress=lambda factor_id: print(f"    neutral-IC {factor_id}", flush=True),
        jobs=jobs,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--runs-dir", default="data/factor_lab/validation_runs")
    parser.add_argument("--out", default="data/factor_lab/supplementary_report.json")
    parser.add_argument("--q", type=float, default=0.05, help="BH-FDR level")
    parser.add_argument("--primary-horizon", type=int, default=10)
    parser.add_argument("--factor", action="append", dest="factors", help="restrict to this factor id")
    parser.add_argument("--panel-file", help="extended panel Parquet, enables industry-neutral IC")
    parser.add_argument("--factor-file", help="factor value Parquet, or a directory of parts")
    parser.add_argument(
        "--jobs",
        type=int,
        default=1,
        help="processes for the per-factor industry-neutral maths. Each factor needs two "
             "per-date Spearman passes over ~1,600 dates (~17 s), so hundreds of factors "
             "single-threaded is hours on the critical path. Uses fork, so the ~3 GB panel is "
             "shared rather than copied; ignored where fork is unavailable.",
    )
    parser.add_argument(
        "--neutral-for-all",
        action="store_true",
        help="compute industry-neutral retention for every result, not just the factors that "
             "passed. The default restricts it to the delivered set, which is a ~3x saving at "
             "the real scale; FDR is unaffected either way because it reads every p-value.",
    )
    parser.add_argument(
        "--neutralize-returns",
        action="store_true",
        help="also remove within-industry return means (stricter)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    runs_dir = Path(args.runs_dir)
    out_path = Path(args.out)

    print(f"loading validation results from {runs_dir}")
    results = load_results(runs_dir, args.factors)
    print(f"  {len(results)} result(s)")

    neutral: dict | None = None
    if args.panel_file or args.factor_file:
        if not (args.panel_file and args.factor_file):
            raise SystemExit("--panel-file and --factor-file must be supplied together")
        print("computing industry-neutral retention")
        neutral_targets = results
        if not args.neutral_for_all:
            # The gates already ran; only the factors that cleared them are delivered, and the
            # column is only reported for those. FDR is computed over every p-value regardless,
            # so this narrows the work without narrowing the correction.
            neutral_targets = [
                result
                for result in results
                if result.get("status") == "validated" and not result.get("failed_gates")
            ]
            print(
                f"  restricting retention to the {len(neutral_targets)} factor(s) that passed "
                f"every frozen gate (of {len(results)}); pass --neutral-for-all to widen it"
            )
        neutral = compute_neutral_ic(
            neutral_targets,
            Path(args.panel_file),
            Path(args.factor_file),
            horizon=args.primary_horizon,
            neutralize_returns=args.neutralize_returns,
            jobs=args.jobs,
        )
    else:
        print("  industry-neutral IC skipped (no --panel-file/--factor-file)")

    report = build_supplementary_report(
        results, q=args.q, primary_horizon=args.primary_horizon, neutral_ic=neutral
    )
    report["generated_at"] = datetime.now(CN_TZ).isoformat(timespec="seconds")
    report["source_runs_dir"] = str(runs_dir)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path = out_path.with_suffix(".md")
    markdown_path.write_text(render_markdown(report), encoding="utf-8")

    summary = report["summary"]
    print(f"\nwrote {out_path}")
    print(f"wrote {markdown_path}")
    print(f"  submitted : {summary['n_submitted']}")
    print(f"  testable  : {summary['n_tested']}")
    print(f"  pass FDR  : {summary['n_accepted']}")
    print(f"  fail FDR  : {summary['n_rejected']}")
    print(
        "\nnote: passing FDR is necessary, not sufficient. A factor still has to "
        "clear all eight frozen gates."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
