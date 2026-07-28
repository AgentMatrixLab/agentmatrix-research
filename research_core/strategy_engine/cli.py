from __future__ import annotations

import argparse
import json

from research_core.strategy_engine.alpha_strategy import build_alpha_strategy_package


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AgentMatrix strategy engine CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_parser = subparsers.add_parser("build-alpha-strategy", help="Build target weights from a validated factor run")
    build_parser.add_argument("--validated-run", required=True, help="Path to factor_lab job JSON")
    build_parser.add_argument("--factors", default="", help="Comma separated factor names; defaults to job requested_factors")
    build_parser.add_argument("--as-of", default="", help="Build a single-snapshot signal on or before this date")
    build_parser.add_argument("--start", default="", help="Optional first signal date for multi-date exports")
    build_parser.add_argument("--end", default="", help="Optional last signal date for multi-date exports")
    build_parser.add_argument(
        "--rebalance-frequency",
        choices=["single", "daily", "weekly", "monthly"],
        default="daily",
        help="Signal schedule; --as-of forces a single snapshot",
    )
    build_parser.add_argument("--top-n", type=int, default=50, help="Number of names to hold on each side")
    build_parser.add_argument("--long-short", action="store_true", help="Build long-short weights instead of long-only")
    build_parser.add_argument("--output-dir", default="", help="Optional output directory")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "build-alpha-strategy":
        factor_names = [item.strip() for item in args.factors.split(",") if item.strip()] if args.factors else None
        payload = build_alpha_strategy_package(
            validated_run_path=args.validated_run,
            factor_names=factor_names,
            as_of=args.as_of,
            start=args.start,
            end=args.end,
            rebalance_frequency=args.rebalance_frequency,
            top_n=args.top_n,
            long_short=args.long_short,
            output_dir=args.output_dir or None,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return


if __name__ == "__main__":
    main()
