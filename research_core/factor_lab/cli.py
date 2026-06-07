from __future__ import annotations

import argparse
import json

from research_core.factor_lab.libraries.alpha101 import alpha101_specs
from research_core.factor_lab.registry import export_library_specs
from research_core.factor_lab.runtime import FactorLabWorkspaceConfig
from research_core.factor_lab.service import get_factor_lab_overview, list_alpha101_factors, run_alpha101_research_job
from research_core.factor_lab.validation import export_proof_template


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AgentMatrix Factor Lab CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-workspace", help="Initialize factor_lab runtime directories")
    subparsers.add_parser("overview", help="Show factor_lab overview")
    subparsers.add_parser("list-alpha101", help="List Alpha101 factor specs and proof status")

    catalog_parser = subparsers.add_parser("export-alpha101", help="Export Alpha101 catalog and spec payload")
    catalog_parser.add_argument("--proof-factor", default="alpha1", help="Also export one proof template for the selected factor")

    run_parser = subparsers.add_parser("run-alpha101-demo", help="Run deterministic Alpha101 research demo")
    run_parser.add_argument(
        "--factors",
        default=",".join([f"alpha{i}" for i in range(1, 11)]),
        help="Comma separated factor names",
    )
    run_parser.add_argument("--n-dates", type=int, default=160, help="Number of business dates in demo panel")
    run_parser.add_argument("--n-codes", type=int, default=8, help="Number of securities in demo panel")
    run_parser.add_argument("--seed", type=int, default=7, help="Random seed for deterministic demo panel")

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

    if args.command == "list-alpha101":
        print(json.dumps({"items": list_alpha101_factors(config)}, ensure_ascii=False, indent=2))
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
            },
            config=config,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return


if __name__ == "__main__":
    main()
