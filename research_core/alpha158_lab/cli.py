from __future__ import annotations

import argparse
import json

from research_core.alpha158_lab.config import Alpha158ResearchConfig
from research_core.alpha158_lab.factors.specs import ALPHA158_BATCHES
from research_core.alpha158_lab.pipeline import run_alpha158_all, run_alpha158_batch, run_alpha158_pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Alpha158 research pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run-pipeline", help="Run Alpha158 first-10 factor research pipeline")
    run_parser.add_argument("--start", default="2020-01-01", help="Requested compute window start (clipped to DB)")
    run_parser.add_argument("--end", default="2026-12-31", help="Requested compute window end (clipped to DB)")
    run_parser.add_argument(
        "--validation-end",
        default="2021-06-11",
        help="Qlib truth accuracy window end only (does not limit factor compute or IC range)",
    )
    run_parser.add_argument("--output-dir", default="")
    run_parser.add_argument("--reload-panel", action="store_true")

    batch_parser = subparsers.add_parser("run-batch", help="Run Alpha158 factor batch pipeline")
    batch_parser.add_argument("--batch-id", default="batch_02", choices=sorted(ALPHA158_BATCHES))
    batch_parser.add_argument("--start", default="2020-01-01", help="Requested compute window start (clipped to DB)")
    batch_parser.add_argument("--end", default="2026-12-31", help="Requested compute window end (clipped to DB)")
    batch_parser.add_argument(
        "--validation-end",
        default="2021-06-11",
        help="Qlib truth accuracy window end only (does not limit factor compute or IC range)",
    )
    batch_parser.add_argument("--output-dir", default="")
    batch_parser.add_argument("--reload-panel", action="store_true")

    init_parser = subparsers.add_parser("init-workspace", help="Create Alpha158 runtime directories")

    all_parser = subparsers.add_parser(
        "run-all",
        help="Run all 16 Alpha158 batches (batch_01..batch_16) in one shot",
    )
    all_parser.add_argument("--start", default="2020-01-01", help="Requested compute window start (clipped to DB)")
    all_parser.add_argument("--end", default="2026-12-31", help="Requested compute window end (clipped to DB)")
    all_parser.add_argument(
        "--validation-end",
        default="2021-06-11",
        help="Qlib truth accuracy window end only (does not limit factor compute or IC range)",
    )
    all_parser.add_argument("--output-dir", default="")
    all_parser.add_argument(
        "--reload-panel",
        action="store_true",
        default=True,
        help="Reload market panel from SmartData on first batch (default: true)",
    )
    all_parser.add_argument(
        "--no-reload-panel",
        action="store_false",
        dest="reload_panel",
        help="Reuse existing market_panel.parquet if present",
    )
    all_parser.add_argument(
        "--start-batch",
        default="batch_01",
        choices=sorted(ALPHA158_BATCHES),
        help="Resume from this batch id (earlier batches are skipped)",
    )
    all_parser.add_argument(
        "--with-master-report",
        action="store_true",
        default=True,
        help="Run generate_alpha158_all_reports.py after all batches (default: true)",
    )
    all_parser.add_argument(
        "--no-master-report",
        action="store_false",
        dest="with_master_report",
        help="Skip master dashboard generation",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "init-workspace":
        cfg = Alpha158ResearchConfig()
        for sub in ("truth", "validation", "effectiveness", "charts", "reports"):
            (cfg.output_dir / sub).mkdir(parents=True, exist_ok=True)
        print(json.dumps({"output_dir": str(cfg.output_dir.resolve())}, ensure_ascii=False, indent=2))
        return

    if args.command in {"run-pipeline", "run-batch", "run-all"}:
        cfg = Alpha158ResearchConfig(
            request_start=args.start,
            request_end=args.end,
            start_date=args.start,
            end_date=args.end,
            validation_end=args.validation_end,
        )
        if args.output_dir:
            from pathlib import Path

            cfg.output_dir = Path(args.output_dir)
        reload_panel = getattr(args, "reload_panel", False)
        if args.command == "run-pipeline":
            payload = run_alpha158_pipeline(cfg, reload_panel=reload_panel)
        elif args.command == "run-batch":
            payload = run_alpha158_batch(
                args.batch_id,
                cfg,
                reload_panel=reload_panel,
            )
        else:
            payload = run_alpha158_all(
                cfg,
                reload_panel=reload_panel,
                start_batch=args.start_batch,
            )
            if args.with_master_report:
                import subprocess
                import sys
                from pathlib import Path

                script = Path(__file__).resolve().parents[2] / "scripts" / "generate_alpha158_all_reports.py"
                proc = subprocess.run([sys.executable, str(script)], check=True)
                payload["master_report_exit_code"] = 0
                payload["master_dashboard"] = str(
                    (cfg.output_dir / "reports" / "master" / "MASTER_DASHBOARD.html").resolve()
                )
        print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()