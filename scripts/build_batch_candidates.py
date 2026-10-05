"""Write the candidate list that the completed shards actually cover.

Why this exists
---------------
`cross_check` verifies that a merged batch's ``candidate_count`` matches the candidate list it
is given, and the merge records that file's digest. The run is authorised for 849 candidates,
but a shard run that stops after N of 213 shards has only evaluated the candidates those
shards held -- so handing the merge the full list makes the batch claim 849 candidates while
its results list holds ~560, and the cross-check reports a genuine inconsistency.

The honest description of a partial run is that the batch is the union of the completed
shards. This writes exactly that list, in the full list's order so the result is deterministic
and diffable, and leaves the full list for the delivery manifest -- which is where the
not-yet-evaluated candidates belong, so the client can see them as `not_run` rather than not
at all.

    python -X utf8 scripts/build_batch_candidates.py \
        --run /home/data/agentmatrix_run \
        --candidates /home/data/agentmatrix_run/candidate_list.csv \
        --output delivery/merged_oos/batch_candidates.csv
"""

from __future__ import annotations

import argparse
import csv
import glob
import sys
from pathlib import Path


class BatchCandidateError(RuntimeError):
    """Raised when the batch scope cannot be described honestly."""


def completed_shard_candidates(run_root: Path) -> tuple[set[str], int, int]:
    """Factor ids held by shards that finished, plus (shards_done, shards_without_list)."""
    completed = sorted(
        Path(path).parent.parent
        for path in glob.glob(str(run_root / "shards" / "shard*" / "oos" / "batch_manifest.json"))
    )
    ids: set[str] = set()
    missing = 0
    for shard in completed:
        listing = shard / "candidate_list.csv"
        if not listing.is_file():
            missing += 1
            continue
        with listing.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                factor_id = str(row.get("factor_id", "")).strip()
                if factor_id:
                    ids.add(factor_id)
    return ids, len(completed), missing


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", required=True, help="the run root holding shards/")
    parser.add_argument("--candidates", required=True, help="the full candidate list")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    run_root = Path(args.run)
    if not (run_root / "shards").is_dir():
        raise BatchCandidateError(f"{run_root}/shards does not exist")

    selected, shards_done, shards_without_list = completed_shard_candidates(run_root)
    if not selected:
        raise BatchCandidateError(
            "no completed shard contributed candidates; there is no batch to describe"
        )

    with Path(args.candidates).open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = [row for row in reader if str(row.get("factor_id", "")).strip() in selected]
    if not rows:
        raise BatchCandidateError(
            "none of the completed shards' candidates appear in the full candidate list; the "
            "two disagree about what was authorised"
        )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"wrote {output}")
    print(f"  shards completed      : {shards_done}")
    print(f"  shards without a list : {shards_without_list}")
    print(f"  candidates in batch   : {len(rows)} of {len(selected)} ids held "
          f"({len(selected) - len(rows)} not found in the full list)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
