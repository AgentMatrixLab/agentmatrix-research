#!/usr/bin/env python3
"""Cross-check a batch run against its own artifacts, independently re-deriving every hash.

Prints every inconsistency it finds (factor, check, expected, actual). Exit codes:
  0 = no inconsistency, 5 = inconsistencies found, 2 = could not cross-check (bad input).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from research_core.factor_lab.cross_check import CrossCheckError, cross_check  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-manifest", required=True)
    parser.add_argument("--panel-file", default="")
    parser.add_argument("--factor-file", default="")
    parser.add_argument("--candidates", default="")
    parser.add_argument("--factor-catalog", default="")
    parser.add_argument("--package-manifest", default="")
    parser.add_argument("--config", default="")
    parser.add_argument("--output", default="", help="Optional path to write the JSON report")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = cross_check(
            batch_manifest=args.batch_manifest,
            panel_file=args.panel_file or None,
            factor_file=args.factor_file or None,
            candidates_path=args.candidates or None,
            factor_catalog=args.factor_catalog or None,
            package_manifest=args.package_manifest or None,
            config_path=args.config or None,
        )
    except CrossCheckError as exc:
        print(json.dumps({"status": "error", "reason": str(exc)}, ensure_ascii=False, indent=2))
        return 2

    if args.output:
        Path(args.output).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 5 if payload["finding_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
