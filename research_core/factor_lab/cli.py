from __future__ import annotations

import argparse
import json

from research_core.factor_lab.libraries.alpha101 import IMPLEMENTED_ALPHA101_FACTORS, alpha101_specs
from research_core.factor_lab.libraries.factor_sets import WQ101_ALPHA_1_10
from research_core.factor_lab.libraries.gtja191 import IMPLEMENTED_GTJA191_FACTORS
from research_core.factor_lab.registry import export_library_specs
from research_core.factor_lab.runtime import FactorLabWorkspaceConfig
from research_core.factor_lab.service import (
    check_amazingdata,
    export_alpha101_truth_template,
    get_factor_lab_overview,
    list_alpha101_factors,
    list_factor_set_factors,
    run_factor_set_research_job,
    run_alpha101_research_job,
    run_alpha101_truth_proof_batch,
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
    list_factor_set_parser.add_argument("--factor-set", choices=["wq101", "gtja191"], required=True)

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

    run_parser = subparsers.add_parser("run-alpha101-demo", help="Run deterministic Alpha101 research demo")
    run_parser.add_argument(
        "--factors",
        default=",".join(IMPLEMENTED_ALPHA101_FACTORS),
        help="Comma separated factor names",
    )
    run_parser.add_argument("--n-dates", type=int, default=160, help="Number of business dates in demo panel")
    run_parser.add_argument("--n-codes", type=int, default=8, help="Number of securities in demo panel")
    run_parser.add_argument("--seed", type=int, default=7, help="Random seed for deterministic demo panel")
    run_parser.add_argument("--truth-csv", default="", help="Optional external truth CSV for factor-by-factor comparison")
    run_parser.add_argument("--truth-tolerance", type=float, default=1e-12, help="Absolute tolerance for truth comparison")

    factor_set_parser = subparsers.add_parser("run-factor-set-demo", help="Run deterministic WQ101/GTJA191 factor_lab demo")
    factor_set_parser.add_argument("--factor-set", choices=["wq101", "gtja191"], required=True)
    factor_set_parser.add_argument(
        "--factors",
        default="",
        help="Comma separated factor names. Defaults to WQ101 Alpha1-10 or GTJA191 Alpha1-10.",
    )
    factor_set_parser.add_argument("--n-dates", type=int, default=160, help="Number of business dates in demo panel")
    factor_set_parser.add_argument("--n-codes", type=int, default=8, help="Number of securities in demo panel")
    factor_set_parser.add_argument("--seed", type=int, default=7, help="Random seed for deterministic demo panel")
    factor_set_parser.add_argument("--truth-csv", default="", help="Optional external truth CSV for factor-by-factor comparison")
    factor_set_parser.add_argument("--truth-tolerance", type=float, default=1e-12, help="Absolute tolerance for truth comparison")

    research_parser = subparsers.add_parser("run-factor-research", help="Run factor_lab research on demo or amazingdata")
    research_parser.add_argument("--factor-set", choices=["wq101", "gtja191"], required=True)
    research_parser.add_argument("--data-source", choices=["demo", "amazingdata"], default="demo")
    research_parser.add_argument("--factors", default="", help="Comma separated factor names")
    research_parser.add_argument("--start", default="", help="Start date for amazingdata jobs")
    research_parser.add_argument("--end", default="", help="End date for amazingdata jobs")
    research_parser.add_argument("--universe", default="csi800", help="Universe label for amazingdata selection")
    research_parser.add_argument("--symbols", default="", help="Comma separated explicit symbols")
    research_parser.add_argument("--max-symbols", type=int, default=300, help="Maximum symbols selected from amazingdata")
    research_parser.add_argument("--n-dates", type=int, default=160, help="Demo dates")
    research_parser.add_argument("--n-codes", type=int, default=8, help="Demo codes")
    research_parser.add_argument("--seed", type=int, default=7, help="Demo random seed")
    research_parser.add_argument("--horizon", type=int, default=1, help="Forward return horizon")
    research_parser.add_argument("--quantiles", type=int, default=5, help="Validation quantiles")
    research_parser.add_argument("--warmup-calendar-days", type=int, default=420, help="Warmup calendar days for real data")
    research_parser.add_argument("--env-file", default="", help="Optional amazingdata env file path")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    config = FactorLabWorkspaceConfig()

    if args.command == "init-workspace":
        payload = {key: str(value) for key, value in config.ensure_directories().items()}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    if args.command == "export-alpha101":
        specs = alpha101_specs()
        payload = export_library_specs(config=config, library="alpha101", specs=specs)
        proof_factor = next((item for item in specs if item.factor_name == args.proof_factor), specs[0])
        payload["proof_path"] = export_proof_template(config=config, spec=proof_factor)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    if args.command == "overview":
        print(json.dumps(get_factor_lab_overview(config), ensure_ascii=False, indent=2))
        return

    if args.command == "check-amazingdata":
        payload = {"env_file": args.env_file} if args.env_file else {}
        print(json.dumps(check_amazingdata(payload), ensure_ascii=False, indent=2))
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
        payload = validate_alpha101_truth_csv(
            {
                "factor_names": factor_names,
                "truth_csv_path": args.truth_csv,
            },
            config=config,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    if args.command == "run-alpha101-proof-batch":
        factor_names = [item.strip() for item in args.factors.split(",") if item.strip()]
        payload = run_alpha101_truth_proof_batch(
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

    if args.command == "list-alpha101":
        print(json.dumps({"items": list_alpha101_factors(config)}, ensure_ascii=False, indent=2))
        return

    if args.command == "list-factor-set":
        print(json.dumps({"items": list_factor_set_factors(args.factor_set, config)}, ensure_ascii=False, indent=2))
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
        default_factors = WQ101_ALPHA_1_10 if args.factor_set == "wq101" else IMPLEMENTED_GTJA191_FACTORS
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

    if args.command == "run-factor-research":
        default_factors = WQ101_ALPHA_1_10 if args.factor_set == "wq101" else IMPLEMENTED_GTJA191_FACTORS
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


if __name__ == "__main__":
    main()
