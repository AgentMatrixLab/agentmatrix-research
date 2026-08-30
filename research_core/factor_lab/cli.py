from __future__ import annotations

import argparse
import json

from research_core.factor_lab.libraries.alpha101 import IMPLEMENTED_ALPHA101_FACTORS, alpha101_specs
from research_core.factor_lab.libraries.factor_sets import WQ101_ALPHA_1_10
from research_core.factor_lab.libraries.gtja191 import IMPLEMENTED_GTJA191_FACTORS
from research_core.factor_lab.registry import export_library_specs
from research_core.factor_lab.runtime import FactorLabWorkspaceConfig
from research_core.factor_lab.libraries.jq_gm import JQ_GM_IMPLEMENTED_FACTORS
from research_core.factor_lab.service import (
    check_amazingdata,
    export_alpha101_truth_template,
    get_factor_lab_overview,
    list_alpha101_factors,
    list_factor_set_factors,
    list_jq_gm_factors,
    run_factor_set_research_job,
    run_factor_set_real_data_job,
    run_alpha101_research_job,
    run_alpha101_truth_proof_batch,
    run_jq_gm_research_job,
    run_jq_gm_truth_proof_batch,
    validate_alpha101_truth_csv,
)
from research_core.factor_lab.validation import export_proof_template


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AgentMatrix Factor Lab CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-workspace", help="Initialize factor_lab runtime directories")
    subparsers.add_parser("overview", help="Show factor_lab overview")
    check_parser = subparsers.add_parser("check-amazingdata", help="Check amazingdata ClickHouse connectivity")
    check_parser.add_argument("--env-file", default="", help="Optional ClickHouse env file path")

    subparsers.add_parser("list-alpha101", help="List Alpha101 factor specs and proof status")
    list_factor_set_parser = subparsers.add_parser("list-factor-set", help="List WQ101 or GTJA191 factor specs and proof status")
    list_factor_set_parser.add_argument("--factor-set", choices=["wq101", "gtja191", "alpha158", "barra"], required=True)

    # ── jq_gm subcommands ──
    _add_jq_gm_subparsers(subparsers)

    catalog_parser = subparsers.add_parser("export-alpha101", help="Export Alpha101 catalog and spec payload")
    catalog_parser.add_argument("--proof-factor", default="alpha1", help="Also export one proof template for the selected factor")

    truth_parser = subparsers.add_parser(
        "export-alpha101-truth-template",
        help="Export a schema-ready Alpha101 truth CSV template",
    )
    truth_parser.add_argument(
        "--factors",
        default=",".join(IMPLEMENTED_ALPHA101_FACTORS),
        help="Comma separated factor names",
    )
    truth_parser.add_argument("--n-dates", type=int, default=160, help="Number of business dates in template panel")
    truth_parser.add_argument("--n-codes", type=int, default=8, help="Number of securities in template panel")
    truth_parser.add_argument("--seed", type=int, default=7, help="Random seed for deterministic template panel")
    truth_parser.add_argument("--template-name", default="", help="Optional custom base name for the exported truth CSV")

    validate_parser = subparsers.add_parser(
        "validate-alpha101-truth",
        help="Validate an Alpha101 truth CSV before running proof batch",
    )
    validate_parser.add_argument(
        "--factors",
        default=",".join(IMPLEMENTED_ALPHA101_FACTORS),
        help="Comma separated factor names",
    )
    validate_parser.add_argument("--truth-csv", required=True, help="Truth CSV to validate")

    batch_parser = subparsers.add_parser(
        "run-alpha101-proof-batch",
        help="Run Alpha101 full truth/proof batch with an external truth CSV",
    )
    batch_parser.add_argument(
        "--factors",
        default=",".join(IMPLEMENTED_ALPHA101_FACTORS),
        help="Comma separated factor names",
    )
    batch_parser.add_argument("--truth-csv", required=True, help="External truth CSV aligned to the requested factors")
    batch_parser.add_argument("--truth-tolerance", type=float, default=1e-12, help="Absolute tolerance for truth comparison")
    batch_parser.add_argument("--n-dates", type=int, default=420, help="Number of business dates in demo panel")
    batch_parser.add_argument("--n-codes", type=int, default=8, help="Number of securities in demo panel")
    batch_parser.add_argument("--seed", type=int, default=29, help="Random seed for deterministic demo panel")

    run_demo_parser = subparsers.add_parser("run-alpha101-demo", help="Run Alpha101 demo research job")
    run_demo_parser.add_argument("--factors", default="alpha1,alpha2,alpha3", help="Factor names")
    run_demo_parser.add_argument("--n-dates", type=int, default=252)
    run_demo_parser.add_argument("--n-codes", type=int, default=50)
    run_demo_parser.add_argument("--seed", type=int, default=42)
    run_demo_parser.add_argument("--truth-csv", default="")
    run_demo_parser.add_argument("--truth-tolerance", type=float, default=1e-12)

    run_factor_set_parser = subparsers.add_parser("run-factor-set-demo", help="Run factor set demo")
    run_factor_set_parser.add_argument("--factor-set", choices=["wq101", "gtja191", "alpha158", "barra"], required=True)
    run_factor_set_parser.add_argument("--factors", default="")
    run_factor_set_parser.add_argument("--n-dates", type=int, default=252)
    run_factor_set_parser.add_argument("--n-codes", type=int, default=50)
    run_factor_set_parser.add_argument("--seed", type=int, default=42)
    run_factor_set_parser.add_argument("--truth-csv", default="")
    run_factor_set_parser.add_argument("--truth-tolerance", type=float, default=1e-12)

    # ── PR #44: run-factor-set-real (real Quant API kline data) ──
    real_parser = subparsers.add_parser("run-factor-set-real", help="Run WQ101/GTJA191 on real Quant API kline data")
    real_parser.add_argument("--factor-set", choices=["wq101", "gtja191"], default="gtja191")
    real_parser.add_argument("--factors", default="alpha1,alpha2,alpha3", help="Comma separated factor names")
    real_parser.add_argument("--symbols", default="", help="Optional comma separated symbols, e.g. 000001.SZ,000002.SZ")
    real_parser.add_argument("--n-symbols", type=int, default=12, help="Number of symbols to auto-discover when --symbols is empty")
    real_parser.add_argument("--n-dates", type=int, default=80, help="Number of daily bars per symbol")
    real_parser.add_argument("--quantile", type=float, default=0.2, help="Top/bottom quantile for long-short backtest")

    run_research_parser = subparsers.add_parser("run-factor-research", help="Run factor research with real or demo data")
    run_research_parser.add_argument("--factor-set", choices=["wq101", "gtja191", "alpha158", "barra"], required=True)
    run_research_parser.add_argument("--factors", default="")
    run_research_parser.add_argument("--data-source", choices=["demo", "amazingdata"], default="demo")
    run_research_parser.add_argument("--start", default="")
    run_research_parser.add_argument("--end", default="")
    run_research_parser.add_argument("--universe", default="csi300")
    run_research_parser.add_argument("--symbols", default="")
    run_research_parser.add_argument("--max-symbols", type=int, default=300)
    run_research_parser.add_argument("--n-dates", type=int, default=252)
    run_research_parser.add_argument("--n-codes", type=int, default=50)
    run_research_parser.add_argument("--seed", type=int, default=42)
    run_research_parser.add_argument("--horizon", type=int, default=5)
    run_research_parser.add_argument("--quantiles", type=int, default=5)
    run_research_parser.add_argument("--warmup-calendar-days", type=int, default=504)
    run_research_parser.add_argument("--env-file", default="")

    # ── NEW: explore command (agent-first one-click pipeline) ──
    explore_parser = subparsers.add_parser(
        "explore",
        help="🚀 One-click factor exploration with auto-data + validation gates",
    )
    explore_parser.add_argument(
        "--goal", default="",
        help="Human-readable goal, e.g. 'low volatility quality factors'",
    )
    explore_parser.add_argument(
        "--universe", default="csi300",
        choices=["csi300", "csi500", "csi800", "all"],
        help="Stock universe (default: csi300)",
    )
    explore_parser.add_argument(
        "--factor-set", default="alpha101",
        choices=["alpha101", "wq101", "gtja191", "alpha158", "barra"],
        help="Factor family to explore",
    )
    explore_parser.add_argument(
        "--factors", default="",
        help="Comma-separated factor names; omit for auto top-10",
    )
    explore_parser.add_argument(
        "--start", default="2023-01-01",
        help="Start date for data",
    )
    explore_parser.add_argument(
        "--end", default="2025-12-31",
        help="End date for data",
    )
    explore_parser.add_argument(
        "--top-n", type=int, default=10,
        help="Number of top factors to report",
    )
    explore_parser.add_argument(
        "--cache-dir", default="/tmp/agentmatrix_cache",
        help="Cache directory for market data",
    )
    explore_parser.add_argument(
        "--output", default="",
        help="Output JSON file path (default: stdout)",
    )
    explore_parser.add_argument(
        "--format", default="json",
        choices=["json", "markdown"],
        help="Output format",
    )

    # ── NEW: gate command (standalone validation gate) ──
    gate_parser = subparsers.add_parser(
        "gate",
        help="🔐 Run validation gates on factor evaluation results",
    )
    gate_parser.add_argument(
        "--input", required=True,
        help="Path to factor evaluation JSON",
    )
    gate_parser.add_argument(
        "--format", default="json",
        choices=["json", "markdown"],
        help="Output format",
    )

    # ── evaluate command ──
    eval_parser = subparsers.add_parser(
        "evaluate",
        help="📊 Full factor IC evaluation (rank IC, decay, turnover, sector neutrality)",
    )
    eval_parser.add_argument("--factor-csv", required=True, help="CSV with date,code,factor_value,next_return,[sector]")
    eval_parser.add_argument("--factor-name", default="factor", help="Factor display name")
    eval_parser.add_argument("--sector-col", default="sector", help="Sector column name (if available)")
    eval_parser.add_argument("--output-json", default="", help="Optional JSON output path")
    eval_parser.add_argument("--ic-threshold", type=float, default=0.02, help="Min |IC| to pass")
    eval_parser.add_argument("--turnover-warn", type=float, default=0.7, help="Turnover rate warning threshold")

    # ── auto-mine command ──
    auto_mine_parser = subparsers.add_parser(
        "auto-mine",
        help="⛏️  Automatic factor mining loop (compile → real IC evaluation → dedup → feedback)",
    )
    auto_mine_parser.add_argument("--source", default="auto",
                                  choices=["auto", "cache", "api", "parquet", "synthetic"],
                                  help="Panel data source (auto: cache → API → synthetic)")
    auto_mine_parser.add_argument("--parquet-path", default="", help="Panel parquet path (source=parquet)")
    auto_mine_parser.add_argument("--mode", default="auto", choices=["auto", "llm", "gp", "builtin"],
                                  help="Candidate generator (auto: LLM → builtin fallback)")
    auto_mine_parser.add_argument("--theme", default="量价因子", help="Mining theme for LLM prompts")
    auto_mine_parser.add_argument("--rounds", type=int, default=2, help="Feedback loop rounds")
    auto_mine_parser.add_argument("--count", type=int, default=8, help="Candidates per round")
    auto_mine_parser.add_argument("--population", type=int, default=24, help="GP population size (mode=gp)")
    auto_mine_parser.add_argument("--generations", type=int, default=5, help="GP generations (mode=gp)")
    auto_mine_parser.add_argument("--horizon", type=int, default=5, help="Forward-return horizon (days)")
    auto_mine_parser.add_argument("--n-symbols", type=int, default=30, help="Panel symbols (API/synthetic)")
    auto_mine_parser.add_argument("--n-dates", type=int, default=250, help="Panel dates (API/synthetic)")
    auto_mine_parser.add_argument("--refresh-cache", action="store_true", help="Force panel cache re-download")

    return parser


def _add_jq_gm_subparsers(subparsers) -> None:
    """Register jq_gm CLI subcommands.

    Follows the same argparse pattern as alpha101. Separated into a helper
    so build_parser() stays readable as more libraries are added.
    """
    subparsers.add_parser("list-jq-gm", help="List jq_gm factor specs and proof status")

    export_parser = subparsers.add_parser(
        "export-jq-gm", help="Export jq_gm catalog and spec payload"
    )
    export_parser.add_argument(
        "--proof-factor",
        default="market_cap",
        help="Also export one proof template for the selected factor",
    )

    demo_parser = subparsers.add_parser(
        "run-jq-gm-demo", help="Run deterministic jq_gm research demo"
    )
    demo_parser.add_argument(
        "--factors",
        default=",".join(JQ_GM_IMPLEMENTED_FACTORS),
        help="Comma separated factor names",
    )
    demo_parser.add_argument(
        "--n-dates", type=int, default=160,
        help="Number of business dates in demo panel",
    )
    demo_parser.add_argument(
        "--n-codes", type=int, default=8,
        help="Number of securities in demo panel",
    )
    demo_parser.add_argument(
        "--seed", type=int, default=7,
        help="Random seed for deterministic demo panel",
    )
    demo_parser.add_argument(
        "--truth-csv", default="",
        help="Optional external truth CSV for factor-by-factor comparison",
    )
    demo_parser.add_argument(
        "--truth-tolerance", type=float, default=1e-12,
        help="Absolute tolerance for truth comparison",
    )

    batch_parser = subparsers.add_parser(
        "run-jq-gm-proof-batch",
        help="Run jq_gm full truth/proof batch with an external truth CSV",
    )
    batch_parser.add_argument(
        "--factors",
        default=",".join(JQ_GM_IMPLEMENTED_FACTORS),
        help="Comma separated factor names",
    )
    batch_parser.add_argument(
        "--truth-csv", required=True,
        help="External truth CSV aligned to the requested factors",
    )
    batch_parser.add_argument(
        "--truth-tolerance", type=float, default=1e-12,
        help="Absolute tolerance for truth comparison",
    )
    batch_parser.add_argument(
        "--n-dates", type=int, default=420,
        help="Number of business dates in demo panel",
    )
    batch_parser.add_argument(
        "--n-codes", type=int, default=8,
        help="Number of securities in demo panel",
    )
    batch_parser.add_argument(
        "--seed", type=int, default=29,
        help="Random seed for deterministic demo panel",
    )


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    config = FactorLabWorkspaceConfig()

    if args.command == "init-workspace":
        payload = {key: str(value) for key, value in config.ensure_directories().items()}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    if args.command == "overview":
        print(json.dumps(get_factor_lab_overview(config), ensure_ascii=False, indent=2))
        return

    if args.command == "check-amazingdata":
        payload = {"env_file": args.env_file} if args.env_file else {}
        print(json.dumps(check_amazingdata(payload), ensure_ascii=False, indent=2))
        return

    if args.command == "list-alpha101":
        print(json.dumps({"items": list_alpha101_factors(config)}, ensure_ascii=False, indent=2))
        return

    if args.command == "list-factor-set":
        print(json.dumps({"items": list_factor_set_factors(args.factor_set, config)}, ensure_ascii=False, indent=2))
        return

    if args.command == "list-jq-gm":
        print(json.dumps(
            {"items": list_jq_gm_factors(config)},
            ensure_ascii=False, indent=2,
        ))
        return

    if args.command == "export-jq-gm":
        from research_core.factor_lab.libraries.jq_gm import jq_gm_specs as _specs_fn
        specs_list = _specs_fn()
        payload = export_library_specs(
            config=config, library="jq_gm", specs=specs_list,
        )
        proof_factor = next(
            (s for s in specs_list if s.factor_name == args.proof_factor),
            specs_list[0],
        )
        payload["proof_path"] = export_proof_template(
            config=config, spec=proof_factor,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    if args.command == "run-jq-gm-demo":
        factor_names = [
            item.strip() for item in args.factors.split(",") if item.strip()
        ]
        payload = run_jq_gm_research_job(
            {
                "factor_names": factor_names,
                "n_dates": args.n_dates,
                "n_codes": args.n_codes,
                "seed": args.seed,
                "data_source": "demo",
                "truth_csv_path": getattr(args, "truth_csv", ""),
                "truth_tolerance": args.truth_tolerance,
            },
            config=config,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    if args.command == "run-jq-gm-proof-batch":
        factor_names = [
            item.strip() for item in args.factors.split(",") if item.strip()
        ]
        payload = run_jq_gm_truth_proof_batch(
            {
                "factor_names": factor_names,
                "truth_csv_path": args.truth_csv,
                "truth_tolerance": args.truth_tolerance,
                "n_dates": args.n_dates,
                "n_codes": args.n_codes,
                "seed": args.seed,
                "data_source": "demo",
            },
            config=config,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    if args.command == "export-alpha101":
        specs = alpha101_specs()
        payload = export_library_specs(config=config, library="alpha101", specs=specs)
        proof_factor = next((item for item in specs if item.factor_name == args.proof_factor), specs[0])
        payload["proof_path"] = export_proof_template(config=config, spec=proof_factor)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    if args.command == "export-alpha101-truth-template":
        factor_names = [item.strip() for item in args.factors.split(",") if item.strip()]
        payload = export_alpha101_truth_template(
            {
                "factor_names": factor_names,
                "n_dates": args.n_dates,
                "n_codes": args.n_codes,
                "seed": args.seed,
                "template_name": args.template_name,
            },
            config=config,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    if args.command == "validate-alpha101-truth":
        factor_names = [item.strip() for item in args.factors.split(",") if item.strip()]
        payload = validate_alpha101_truth_csv(args.truth_csv, factor_names)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    if args.command == "run-alpha101-proof-batch":
        factor_names = [item.strip() for item in args.factors.split(",") if item.strip()]
        payload = run_alpha101_truth_proof_batch(
            args.truth_csv,
            factor_names=factor_names,
            truth_tolerance=args.truth_tolerance,
            n_dates=args.n_dates,
            n_codes=args.n_codes,
            seed=args.seed,
            config=config,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    if args.command == "run-alpha101-demo":
        factor_names = [item.strip() for item in args.factors.split(",") if item.strip()]
        payload = run_alpha101_research_job(
            {
                "factor_names": factor_names,
                "n_dates": args.n_dates,
                "n_codes": args.n_codes,
                "seed": args.seed,
                "data_source": "demo",
                "truth_csv_path": args.truth_csv,
                "truth_tolerance": args.truth_tolerance,
            },
            config=config,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    if args.command == "run-factor-set-demo":
        if args.factor_set == "wq101":
            default_factors = WQ101_ALPHA_1_10
        elif args.factor_set == "gtja191":
            default_factors = IMPLEMENTED_GTJA191_FACTORS
        else:
            from research_core.factor_lab.libraries.factor_sets import ALPHA158_ALL_FACTORS
            default_factors = ALPHA158_ALL_FACTORS
        factor_names = [item.strip() for item in args.factors.split(",") if item.strip()] if args.factors else list(default_factors)
        payload = run_factor_set_research_job(
            {
                "factor_set": args.factor_set,
                "factor_names": factor_names,
                "n_dates": args.n_dates,
                "n_codes": args.n_codes,
                "seed": args.seed,
                "data_source": "demo",
                "truth_csv_path": args.truth_csv,
                "truth_tolerance": args.truth_tolerance,
            },
            config=config,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    if args.command == "run-factor-set-real":
        factor_names = [item.strip() for item in args.factors.split(",") if item.strip()]
        symbols = [item.strip() for item in args.symbols.split(",") if item.strip()]
        payload = run_factor_set_real_data_job(
            {
                "factor_set": args.factor_set,
                "factor_names": factor_names,
                "symbols": symbols,
                "n_symbols": args.n_symbols,
                "n_dates": args.n_dates,
                "quantile": args.quantile,
            },
            config=config,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    if args.command == "run-factor-research":
        if args.factor_set == "wq101":
            default_factors = WQ101_ALPHA_1_10
        elif args.factor_set == "gtja191":
            default_factors = IMPLEMENTED_GTJA191_FACTORS
        else:
            from research_core.factor_lab.libraries.factor_sets import ALPHA158_ALL_FACTORS
            default_factors = ALPHA158_ALL_FACTORS
        factor_names = [item.strip() for item in args.factors.split(",") if item.strip()] if args.factors else list(default_factors)
        request_payload = {
            "factor_set": args.factor_set,
            "factor_names": factor_names,
            "data_source": args.data_source,
            "start": args.start,
            "end": args.end,
            "universe": args.universe,
            "symbols": args.symbols,
            "max_symbols": args.max_symbols,
            "n_dates": args.n_dates,
            "n_codes": args.n_codes,
            "seed": args.seed,
            "horizon": args.horizon,
            "quantiles": args.quantiles,
            "warmup_calendar_days": args.warmup_calendar_days,
            "env_file": args.env_file,
        }
        payload = run_factor_set_research_job(request_payload, config=config)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    # ── NEW: explore command ─────────────────────────────────
    if args.command == "explore":
        from research_core.factor_lab.agent_pipeline import explore, explore_to_markdown

        factor_list = None
        if args.factors:
            factor_list = [f.strip() for f in args.factors.split(",") if f.strip()]

        result = explore(
            goal=args.goal or f"explore {args.factor_set} on {args.universe}",
            universe=args.universe,
            factor_set=args.factor_set,
            factors=factor_list,
            start=args.start,
            end=args.end,
            top_n=args.top_n,
            cache_dir=args.cache_dir,
            workspace=config,
        )

        if args.format == "markdown":
            print(explore_to_markdown(result))
        else:
            print(json.dumps({
                "gate_verdict": result.gate_verdict,
                "factors_tested": result.factors_tested,
                "factors_passed": result.factors_passed,
                "elapsed_seconds": result.elapsed_seconds,
                "universe": result.universe,
                "n_stocks": result.n_stocks,
                "top_factors": result.top_factors,
                "summary": result.summary,
                "next_actions": result.next_actions,
            }, ensure_ascii=False, indent=2))
        return

    # ── NEW: gate command ────────────────────────────────────
    if args.command == "gate":
        from research_core.factor_lab.validation_gate import ValidationGate

        with open(args.input, "r") as f:
            data = json.load(f)

        gate = ValidationGate()
        factors = data if isinstance(data, list) else data.get("factors", [data])
        verdicts = gate.batch_evaluate(factors)

        if args.format == "markdown":
            print(gate.summary_markdown(verdicts))
        else:
            output = {
                "passed": sum(1 for v in verdicts if v.passed),
                "total": len(verdicts),
                "verdicts": [v.to_dict() for v in verdicts],
            }
            print(json.dumps(output, ensure_ascii=False, indent=2))
        return

    # ── evaluate command handler ──
    if args.command == "evaluate":
        import pandas as pd
        from research_core.factor_lab.evaluation import evaluate_factor, evaluation_summary

        df = pd.read_csv(args.factor_csv)
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])

        report = evaluate_factor(
            df, args.factor_name,
            factor_col="factor_value", return_col="next_return",
            sector_col=args.sector_col if args.sector_col in df.columns else "sector",
            ic_threshold=args.ic_threshold, turnover_warn=args.turnover_warn,
        )

        print(evaluation_summary(report))
        if report.warnings:
            for w in report.warnings:
                print(f"  ⚠️  {w}")
        if args.output_json:
            out = {
                "factor_name": report.factor_name,
                "status": report.status,
                "mean_rank_ic": report.ic_eval.mean_rank_ic if report.ic_eval else None,
                "rank_icir": report.ic_eval.rank_icir if report.ic_eval else None,
                "ic_positive_ratio": report.ic_eval.ic_positive_ratio if report.ic_eval else None,
                "mean_turnover": report.turnover.mean_turnover if report.turnover else None,
                "ic_decay": report.ic_eval.decay_series.to_dict() if report.ic_eval else {},
                "warnings": report.warnings,
            }
            with open(args.output_json, "w") as f:
                json.dump(out, f, indent=2, ensure_ascii=False)
        return

    # ── auto-mine command handler ──
    if args.command == "auto-mine":
        from research_core.factor_lab.auto_mining import (
            load_panel,
            run_mining_loop,
            save_results,
        )

        panel, actual_source = load_panel(
            source=args.source,
            parquet_path=args.parquet_path or None,
            n_symbols=args.n_symbols,
            n_dates=args.n_dates,
            refresh_cache=args.refresh_cache,
        )
        print(f"Panel: {panel['date'].nunique()}d x {panel['code'].nunique()}c "
              f"({actual_source}, source={args.source})")

        if args.mode == "gp":
            from research_core.factor_lab.gp_search import GPFactorMiner

            miner = GPFactorMiner(panel, horizon=args.horizon)
            gp_out = miner.evolve(generations=args.generations, population=args.population)
            winners = gp_out["winners"]
            run_output = {"rounds": [{"round": 1, "results": list(miner.cache.values()),
                                      "feedback": "gp"}],
                         "winners": winners,
                         "all_results": list(miner.cache.values())}
        else:
            run_output = run_mining_loop(
                panel,
                theme=args.theme,
                rounds=args.rounds,
                count_per_round=args.count,
                mode="auto" if args.mode == "auto" else args.mode,
                horizon=args.horizon,
            )

        csv_path = save_results(run_output, panel_source=actual_source)
        print(f"\nResults saved: {csv_path}")
        print(f"Winners: {[r.name for r in run_output['winners']]}")
        return


if __name__ == "__main__":
    main()
