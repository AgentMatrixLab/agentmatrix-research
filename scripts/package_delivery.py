#!/usr/bin/env python3
"""Package the delivery: only factors with status == "validated" get included.

Rejected, errored, needs-human and never-run factors are recorded with their status and reason
so the exclusions are auditable. An empty package exits non-zero instead of shipping nothing.

Never copies a factor that did not pass the frozen gates.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from research_core.factor_lab.package_delivery import (  # noqa: E402
    DeliveryPackagingError,
    build_delivery_package,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, help="Package directory to create")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--batch-manifest", default="", help="batch_manifest.json from validate-batch")
    source.add_argument("--results-root", default="", help="config.output.root directory of per-factor runs")
    parser.add_argument("--candidates", default="", help="candidate_list.csv, to emit factor_catalog.csv too")
    parser.add_argument(
        "--no-copy",
        action="store_true",
        help="Only write package_manifest.json; do not copy factor artifacts",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = build_delivery_package(
            output_dir=args.output_dir,
            batch_manifest=args.batch_manifest or None,
            results_root=args.results_root or None,
            candidates_path=args.candidates or None,
            copy_artifacts=not args.no_copy,
        )
    except DeliveryPackagingError as exc:
        print(json.dumps({"status": "error", "reason": str(exc)}, ensure_ascii=False, indent=2))
        return 2

    printable: dict[str, Any] = {
        "package_manifest": payload["package_manifest_path"],
        "counts": payload["counts"],
        "included_factors": [item["factor_id"] for item in payload["included_factors"]],
        "excluded_factors": [
            {"factor_id": item["factor_id"], "status": item["status"]} for item in payload["excluded_factors"]
        ],
        "factor_catalog_csv": payload["factor_catalog_csv"],
    }
    if "warning" in payload:
        printable["warning"] = payload["warning"]
    print(json.dumps(printable, ensure_ascii=False, indent=2))
    return 0 if payload["included_factors"] else 4


if __name__ == "__main__":
    raise SystemExit(main())
