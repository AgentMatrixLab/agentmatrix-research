#!/usr/bin/env python3
"""Build factor_catalog.csv from a candidate list plus real validation results.

Status comes only from actual runs (a batch manifest or a results root). Factors that were
never run are reported as ``not_run``; nothing is inferred or filled in.
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

from research_core.factor_lab.factor_catalog import (  # noqa: E402
    FactorCatalogError,
    build_factor_catalog,
    write_factor_catalog,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", required=True, help="candidate_list.csv path")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--batch-manifest", default="", help="batch_manifest.json from validate-batch")
    source.add_argument("--results-root", default="", help="config.output.root directory of per-factor runs")
    parser.add_argument("--output", default="factor_catalog.csv", help="Where to write the catalog CSV")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        rows = build_factor_catalog(
            args.candidates,
            batch_manifest=args.batch_manifest or None,
            results_root=args.results_root or None,
        )
    except FactorCatalogError as exc:
        print(json.dumps({"status": "error", "reason": str(exc)}, ensure_ascii=False, indent=2))
        return 2

    path = write_factor_catalog(rows, args.output)
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    payload: dict[str, Any] = {
        "catalog": str(path),
        "rows": len(rows),
        "counts": counts,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
