"""Keep the factor values of passing factors before the shard deletes them.

Why this exists
---------------
`run_one_shard.sh` deletes each shard's factor file when it finishes. At the real scale that
file is ~690 MB for four candidates and 213 shards would be ~147 GB, so it cannot simply be
kept. But the supplementary layer needs VALUES: industry-neutral IC is computed on them, and
the strategy demos need them too. `rebuild_passing_factors.py` recomputes them after the run
-- measured at ~140 s per 4 factors, i.e. **~4.4 hours at 450 factors**, all of it serial and
all of it on the critical path after the shards stop.

Retention moves that work off the critical path. The values already exist while the shard is
validating, so this daemon:

  1. hard-links ``factor_values.parquet`` the moment the shard's build report appears
     (a hard link shares the inode, so it costs no disk and survives the shard's own
     ``rm -f``, which only unlinks its directory entry);
  2. waits for the shard's verdict;
  3. writes a small part holding ONLY the base series of the factors that passed;
  4. verifies the part against the build report, then drops the link.

The shard driver is not modified, so nothing about the running pool changes. If the daemon
misses a shard -- it was not running yet, or the file was already gone -- that shard's factors
are simply absent from the parts, and `rebuild_passing_factors.py` remains the fallback. The
daemon never invents a value and never writes a part it has not verified.

    python -X utf8 scripts/dev/retain_passing_values.py --once
    python -X utf8 scripts/dev/retain_passing_values.py --interval 20
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CN_TZ = timezone(timedelta(hours=8))

VALUE_COLUMNS = ("date", "code", "factor_name", "value")
VARIANT_MARKER = "|window="


def passing_factor_ids(manifest_path: Path, repo: Path = ROOT) -> list[str]:
    """Factors with status validated and no failed gates.

    Imported from the rebuild script rather than re-implemented, so the retained set and the
    rebuilt set cannot drift apart.
    """
    scripts_dir = repo / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from rebuild_passing_factors import passing_factor_ids as canonical  # noqa: PLC0415

    return canonical(manifest_path)


def retain_one(
    shard_dir: Path,
    *,
    retain_root: Path,
    rows_per_series: int | None,
    settled: dict,
    log,
    repo: Path = ROOT,
) -> dict:
    """Handle one shard. Returns a small status dict."""
    tag = shard_dir.name
    raw = shard_dir / "factor_values.parquet"
    sidecar = shard_dir / "factor_values.parquet.json"
    report_path = shard_dir / "build_report.json"
    manifest = shard_dir / "oos" / "batch_manifest.json"
    link = retain_root / "raw" / f"{tag}.parquet"
    part = retain_root / "parts" / f"{tag}.parquet"

    state = {"shard": tag, "action": "none"}

    # --- 1. link the values while they still exist -------------------------------
    if part.exists():
        state["action"] = "already_retained"
        return state

    if raw.is_file() and report_path.is_file() and not part.exists():
        try:
            raw_stat = raw.stat()
            report_stat = report_path.stat()
        except OSError:
            return state
        # A build report older than the factor file means the report is left over from a
        # previous attempt and the file is still being written. Linking on that signal would
        # capture a file whose producer has not finished, so wait for the next pass.
        if report_stat.st_mtime >= raw_stat.st_mtime:
            # Only link a file that was unchanged since the previous pass. A shard that is
            # still streaming rows into the file must not be captured mid-write.
            fingerprint = (raw_stat.st_size, raw_stat.st_mtime, raw_stat.st_ino)
            if settled.get(tag) != fingerprint:
                settled[tag] = fingerprint
                state["action"] = "settling"
                return state
            # Ensure the link points at the CURRENT inode. This must not return early: the
            # verdict may have arrived since the previous pass, and the retention step below
            # is what consumes it.
            current = False
            if link.exists():
                try:
                    current = link.stat().st_ino == raw_stat.st_ino
                except OSError:
                    current = False
                if not current:
                    # A re-run replaced the file: the old link points at a stale inode.
                    link.unlink(missing_ok=True)
            if not current:
                link.parent.mkdir(parents=True, exist_ok=True)
                try:
                    os.link(raw, link)
                    state["action"] = "linked"
                    log(f"  {tag}: linked {raw_stat.st_size / 1e6:.0f} MB")
                except OSError as exc:
                    log(f"  {tag}: link failed: {exc}")
                    return state

    # --- 2/3. once the verdict exists, keep only the passing base series ----------
    if manifest.is_file() and link.is_file() and not part.exists():
        try:
            passed = passing_factor_ids(manifest, repo)
        except (OSError, json.JSONDecodeError) as exc:
            log(f"  {tag}: cannot read verdict: {type(exc).__name__}: {exc}")
            return state

        if not passed:
            link.unlink(missing_ok=True)
            state["action"] = "no_passers"
            log(f"  {tag}: no passing factor; dropped link")
            return state

        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            report = {}
        series_total = int(report.get("series") or 0)
        rows_total = int(report.get("rows") or 0)
        expected_per_series = (
            rows_per_series
            if rows_per_series is not None
            else (rows_total // series_total if series_total else None)
        )

        wanted = set(passed)
        try:
            table = pq.read_table(link, filters=[("factor_name", "in", sorted(wanted))])
        except Exception as exc:  # noqa: BLE001 - report and continue; rebuild is the fallback
            log(f"  {tag}: read failed: {type(exc).__name__}: {exc}")
            return state

        names = table.column("factor_name").to_pylist()
        present = sorted(set(names))
        if not present:
            log(f"  {tag}: none of the {len(wanted)} passing factors are in the factor file")
            link.unlink(missing_ok=True)
            state["action"] = "missing_series"
            return state

        # --- 4. verify before keeping -------------------------------------------
        if expected_per_series:
            counts = {name: names.count(name) for name in present}
            bad = {n: c for n, c in counts.items() if c != expected_per_series}
            if bad:
                log(f"  {tag}: REFUSING, row counts differ from the build report: {bad}")
                return state
            if len(table) != len(present) * expected_per_series:
                log(f"  {tag}: REFUSING, total rows {len(table)} != "
                    f"{len(present)} x {expected_per_series}")
                return state
        if any(VARIANT_MARKER in name for name in present):
            log(f"  {tag}: REFUSING, a perturbation variant leaked into the retained part")
            return state

        part.parent.mkdir(parents=True, exist_ok=True)
        temporary = part.with_suffix(".parquet.partial")
        pq.write_table(table, temporary, compression="zstd")
        os.replace(temporary, part)
        link.unlink(missing_ok=True)
        state["action"] = "retained"
        state["factors"] = len(present)
        state["rows"] = len(table)
        log(f"  {tag}: retained {len(present)} base series "
            f"({len(present)}/{len(wanted)} of the passing set), {len(table):,} rows")
        if len(present) < len(wanted):
            missing = sorted(wanted - set(present))
            log(f"  {tag}: WARNING passing factors with no series: {missing[:5]}")

    return state


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", default="/home/data/agentmatrix_run")
    parser.add_argument("--interval", type=int, default=20)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--rows-per-series", type=int, default=0)
    parser.add_argument(
        "--repo",
        default="/home/data/agentmatrix_run/agentmatrix",
        help="the deployed repository root, for the canonical passing-set rule",
    )
    parser.add_argument("--log", default="")
    args = parser.parse_args(argv)

    run = Path(args.run)
    shards_root = run / "shards"
    retain_root = run / "delivery" / "values"
    log_path = Path(args.log) if args.log else run / "logs" / "retain.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    rows_per_series = args.rows_per_series or None
    repo = Path(args.repo)
    passes = 0
    seen: set[str] = set()
    settled: dict[str, tuple[int, float, int]] = {}

    while True:
        passes += 1
        stamp = datetime.now(CN_TZ).isoformat(timespec="seconds")

        def log(message: str) -> None:
            line = f"[{datetime.now(CN_TZ).isoformat(timespec='seconds')}] {message}"
            print(line, flush=True)
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")

        status = {"retained": 0, "linked": 0, "no_passers": 0, "missing_series": 0}
        if shards_root.is_dir():
            for shard_dir in sorted(shards_root.glob("shard*")):
                if not shard_dir.is_dir():
                    continue
                state = retain_one(
                    shard_dir,
                    retain_root=retain_root,
                    rows_per_series=rows_per_series,
                    settled=settled,
                    log=log,
                    repo=repo,
                )
                action = state.get("action")
                if action in status:
                    status[action] += 1
                if action in ("retained", "no_passers", "missing_series"):
                    seen.add(shard_dir.name)

        parts = list((retain_root / "parts").glob("*.parquet")) if (retain_root / "parts").is_dir() else []
        links = list((retain_root / "raw").glob("*.parquet")) if (retain_root / "raw").is_dir() else []
        summary = {
            "updated_at": stamp,
            "passes": passes,
            "shards_settled": len(seen),
            "parts": len(parts),
            "links_pending": len(links),
            **status,
        }
        (retain_root / "retain_status.json").parent.mkdir(parents=True, exist_ok=True)
        (retain_root / "retain_status.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if status["retained"] or status["linked"] or status["missing_series"]:
            log(f"pass {passes}: {summary}")
        if args.once:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return 0
        time.sleep(max(5, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
