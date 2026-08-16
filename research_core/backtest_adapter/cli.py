from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from contracts.backtest import BacktestRequest, ExternalSimulationRequest
from research_core.backtest_adapter.custom_engine import CustomEngineAdapter
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

    custom_parser = subparsers.add_parser("run-custom", help="Run Chenxi Engine (compatibility command)")
    custom_parser.add_argument("--engine-root", required=True, help="Chenxi Engine directory")
    custom_parser.add_argument("--data-dir", default="", help="Optional Parquet data directory")
    custom_parser.add_argument("--strategy", required=True, help="Legacy strategy display name")
    custom_parser.add_argument("--strategy-id", default="", help="Stable AgentMatrix strategy id")
    custom_parser.add_argument("--strategy-version", default="v1")
    custom_parser.add_argument("--run-id", required=True)
    custom_parser.add_argument("--start", required=True)
    custom_parser.add_argument("--end", required=True)
    custom_parser.add_argument("--benchmark", default="000300.SH")
    custom_parser.add_argument("--initial-cash", type=float, default=1_000_000.0)
    custom_parser.add_argument("--slippage-bps", type=float, default=10.0)
    custom_parser.add_argument("--commission-bps", type=float, default=3.0)
    custom_parser.add_argument("--rebalance-freq", type=int, default=5)
    custom_parser.add_argument(
        "--output",
        default="",
        help="Result JSON path (default: runtime/custom_engine/backtests/<run-id>.json)",
    )
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

    if args.command == "run-custom":
        strategy_id = args.strategy_id or args.strategy
        request = BacktestRequest(
            run_id=args.run_id,
            strategy_id=strategy_id,
            strategy_version=args.strategy_version,
            strategy_params={
                "engine_root": args.engine_root,
                "data_dir": args.data_dir,
                "strategy_name": args.strategy,
                "rebalance_freq": args.rebalance_freq,
            },
            module_path="engine://chenxi",
            start_time=args.start,
            end_time=args.end,
            benchmark=args.benchmark,
            initial_cash=args.initial_cash,
            slippage_bps=args.slippage_bps,
            commission_bps=args.commission_bps,
            execution_engine="chenxi",
        )
        result = CustomEngineAdapter().run(request)
        output_path = Path(args.output) if args.output else Path("runtime/custom_engine/backtests") / f"{args.run_id}.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        result.artifacts["result_json"] = str(output_path)
        serialized = json.dumps(asdict(result), ensure_ascii=False, indent=2)
        output_path.write_text(serialized, encoding="utf-8")
        print(serialized)
        return


if __name__ == "__main__":
    main()
