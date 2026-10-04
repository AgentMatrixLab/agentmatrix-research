#!/usr/bin/env python3
"""Merge shard batch manifests produced by parallel ``validate-batch`` runs.

Verifies that every shard ran on the same code commit, panel, factor file, config and segment,
then concatenates the per-factor verdicts. No verdict is recomputed or altered.
Exit codes: 0 = merged, 2 = shards disagree (refused), 3 = bad input.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from research_core.factor_lab.merge_batches import MergeError, merge_batch_manifests  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shards", nargs="+", required=True, help="Shard batch_manifest.json paths")
    parser.add_argument("--output-dir", required=True, help="Where the merged manifest goes")
    parser.add_argument("--candidates", default="", help="candidate_list.csv (recorded for provenance)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = merge_batch_manifests(
            args.shards,
            output_dir=args.output_dir,
            candidates_path=args.candidates or None,
        )
    except MergeError as exc:
        print(json.dumps({"status": "error", "reason": str(exc)}, ensure_ascii=False, indent=2))
        return 2
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "error", "reason": str(exc)}, ensure_ascii=False, indent=2))
        return 3

    printable = {
        "batch_manifest": payload["batch_manifest_path"],
        "shard_count": payload["shard_count"],
        "candidate_count": payload["candidate_count"],
        "counts": payload["counts"],
        "validated_effective_alpha": payload["validated_effective_alpha"],
        "validated_risk_exposure": payload["validated_risk_exposure"],
    }
    print(json.dumps(printable, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
