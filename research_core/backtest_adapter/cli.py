from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from contracts.backtest import ExternalSimulationRequest
from research_core.backtest_adapter.external_simulation import (
    package_external_simulation,
    parse_external_simulation_result,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AgentMatrix external simulation packaging CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    package_parser = subparsers.add_parser("package-external-sim", help="Package signals for GM/PTrade/QMT simulation")
    package_parser.add_argument("--engine", choices=["gm", "ptrade", "qmt"], required=True)
    package_parser.add_argument("--strategy", default="", help="Strategy id")
    package_parser.add_argument("--signal-path", required=True, help="Target weights CSV")
    package_parser.add_argument("--run-id", default="", help="External simulation run id")
    package_parser.add_argument("--start", required=True, help="Simulation start time")
    package_parser.add_argument("--end", required=True, help="Simulation end time")
    package_parser.add_argument("--benchmark", default="", help="Benchmark symbol")
    package_parser.add_argument("--initial-cash", type=float, default=1_000_000.0)
    package_parser.add_argument("--slippage-bps", type=float, default=0.0)
    package_parser.add_argument("--commission-bps", type=float, default=0.0)
    package_parser.add_argument("--output-dir", default="", help="Optional package output directory")

    parse_parser = subparsers.add_parser("parse-external-result", help="Parse an external terminal result file")
    parse_parser.add_argument("--engine", choices=["gm", "ptrade", "qmt"], required=True)
    parse_parser.add_argument("--run-id", required=True)
    parse_parser.add_argument("--result-path", required=True)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "package-external-sim":
        strategy_id = args.strategy or args.run_id or "alpha_strategy"
        run_id = args.run_id or f"{strategy_id}_{args.engine}"
        request = ExternalSimulationRequest(
            run_id=run_id,
            engine=args.engine,
            strategy_id=strategy_id,
            strategy_version="v1",
            signal_path=args.signal_path,
            start_time=args.start,
            end_time=args.end,
            benchmark=args.benchmark,
            initial_cash=args.initial_cash,
            slippage_bps=args.slippage_bps,
            commission_bps=args.commission_bps,
        )
        package = package_external_simulation(request, output_dir=args.output_dir or None)
        print(json.dumps(asdict(package), ensure_ascii=False, indent=2))
        return

    if args.command == "parse-external-result":
        result = parse_external_simulation_result(
            run_id=args.run_id,
            engine=args.engine,
            result_path=args.result_path,
        )
        print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
        return


if __name__ == "__main__":
    main()
