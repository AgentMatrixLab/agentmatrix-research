"""Mirror the server's runtime evidence outside the deploy directory.

Why this exists
---------------
`configs/validation_gates.yaml` (frozen) writes each factor's validation result to
``<repo>/data/factor_lab/validation_runs/<factor_id>/validation_result.json`` -- *inside*
the directory that `upload_repo.py` wipes and re-extracts on every deploy. The server tree
is not a git checkout and ``data/`` is gitignored, so that evidence is untracked and a
deploy destroys it.

That is not hypothetical. An upload during the 213-shard run deleted the results of every
shard that had already finished. Because scoring reads ``--runs-dir`` to assign a tier, and
`in_delivery_package` requires tier S or A, the delivery would have been built from the
handful of results that happened to land after the upload -- with no error, just a smaller
package. FDR is a batch statistic over the same directory, so the badge would have been
computed over the wrong batch as well.

Two defences, because this failure mode is silent:
  1. `upload_repo.py` now preserves ``data/`` across the wipe.
  2. This mirror keeps a copy outside the deploy directory entirely, and it only ever
     adds -- a wipe at the source cannot propagate to the mirror.

    python -X utf8 scripts/dev/mirror_runtime_data.py --once
    python -X utf8 scripts/dev/mirror_runtime_data.py --interval 60
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

CN_TZ = timezone(timedelta(hours=8))


def mirror_tree(source: Path, target: Path) -> dict:
    """Copy files that are new or changed. Never deletes, never follows a wipe."""
    copied = skipped = failed = 0
    bytes_copied = 0
    if not source.exists():
        return {"copied": 0, "skipped": 0, "failed": 0, "bytes": 0, "source_present": False}

    for root, _dirs, files in os.walk(source):
        relative = Path(root).relative_to(source)
        destination_dir = target / relative
        for name in files:
            candidate = Path(root) / name
            destination = destination_dir / name
            try:
                stat = candidate.stat()
            except OSError:
                failed += 1
                continue
            if destination.exists():
                try:
                    existing = destination.stat()
                    if existing.st_size == stat.st_size and existing.st_mtime >= stat.st_mtime:
                        skipped += 1
                        continue
                except OSError:
                    pass
            try:
                destination_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(candidate, destination)
                copied += 1
                bytes_copied += stat.st_size
            except OSError:
                failed += 1
    return {
        "copied": copied,
        "skipped": skipped,
        "failed": failed,
        "bytes": bytes_copied,
        "source_present": True,
    }


def count_files(root: Path) -> int:
    if not root.exists():
        return 0
    return sum(len(files) for _root, _dirs, files in os.walk(root))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", default="/home/data/agentmatrix_run/agentmatrix")
    parser.add_argument("--mirror-root", default="/home/data/agentmatrix_run/runtime_mirror")
    parser.add_argument("--interval", type=int, default=60, help="seconds between passes")
    parser.add_argument("--once", action="store_true", help="one pass, then exit")
    parser.add_argument("--status", default="", help="where to write the status JSON")
    args = parser.parse_args(argv)

    repo = Path(args.repo)
    mirror_root = Path(args.mirror_root)
    source = repo / "data"
    target = mirror_root / "data"
    status_path = Path(args.status) if args.status else mirror_root / "mirror_status.json"
    status_path.parent.mkdir(parents=True, exist_ok=True)

    passes = 0
    while True:
        passes += 1
        result = mirror_tree(source, target)
        # Also carry the revision stamp, so the mirror records which code produced it.
        stamp = repo / "COMMIT"
        if stamp.is_file():
            try:
                shutil.copy2(stamp, mirror_root / "COMMIT")
            except OSError:
                pass
        runs = target / "factor_lab" / "validation_runs"
        status = {
            "updated_at": datetime.now(CN_TZ).isoformat(timespec="seconds"),
            "passes": passes,
            "source": str(source),
            "target": str(target),
            "results_in_source": count_files(runs),
            "results_in_mirror": count_files(runs),
            **result,
        }
        status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
        print(
            f"[{status['updated_at']}] pass {passes}: source_runs={status['results_in_source']} "
            f"mirror_runs={status['results_in_mirror']} copied={result['copied']} "
            f"failed={result['failed']}",
            flush=True,
        )
        if args.once:
            return 0
        time.sleep(max(5, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
