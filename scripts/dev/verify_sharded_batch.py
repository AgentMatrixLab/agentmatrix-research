"""Verify the sharded validate-batch + merge path, including its refusals.

Throughput measurement made sharding mandatory: the frozen validator costs ~27 s
per factor, so a 913-factor run is hours serial and needs to be spread across
cores. That promoted `merge_batch_manifests.py` from a nice-to-have to the
critical path, and a merge that silently accepts shards which ran on different
inputs would be worse than no merge at all -- the counts would look fine and the
evidence would be incoherent.

So this checks both directions:

  positive  three disjoint shards run in parallel, merge cleanly, and the merged
            manifest's per-factor set and status counts equal the union of the
            shards' own results;
  negative  a shard whose panel hash disagrees is REFUSED (exit 2);
            a duplicated factor across shards is REFUSED (exit 2).

    python -X utf8 scripts/dev/verify_sharded_batch.py
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "dev"))

import rehearse_full_pipeline as rehearsal  # noqa: E402

SHARD_COUNT = 3
PANEL_ROW_BUDGET = 40  # codes; enough for the frozen minimum_cross_section


def run(command: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(command, cwd=ROOT, capture_output=True, text=True)


def prepare(work: Path, seed: int) -> dict[str, Path]:
    work.mkdir(parents=True, exist_ok=True)
    rehearsal.N_CODES = PANEL_ROW_BUDGET
    panel = rehearsal.build_panel(seed)
    panel_path = rehearsal.write_panel(panel, work)
    table, meta = rehearsal.compute_factors(panel)
    factor_path = rehearsal.write_factor_table(table, meta["declared"], work)
    candidates = rehearsal.write_candidate_list(meta["computed"], work)
    config = rehearsal.write_rehearsal_config(work)
    return {
        "panel": panel_path,
        "factors": factor_path,
        "candidates": candidates,
        "config": config,
        "computed": meta["computed"],
    }


def split_candidates(candidates: Path, work: Path, ids: list[str], shards: int) -> list[Path]:
    frame = pd.read_csv(candidates, dtype=str, encoding="utf-8")
    paths: list[Path] = []
    for index in range(shards):
        subset = frame.iloc[index :: shards]
        shard_dir = work / f"shard{index}"
        shard_dir.mkdir(parents=True, exist_ok=True)
        path = shard_dir / "candidate_list.csv"
        subset.to_csv(path, index=False, encoding="utf-8")
        paths.append(path)
    return paths


def validate_shard(inputs: dict[str, Path], candidate_path: Path, work: Path, index: int) -> dict:
    shard_dir = work / f"shard{index}"
    command = [
        sys.executable, "-X", "utf8", "-m", "research_core.factor_lab.cli", "validate-batch",
        "--candidates", str(candidate_path),
        "--config", str(inputs["config"]),
        "--panel-file", str(inputs["panel"]),
        "--factor-file", str(inputs["factors"]),
        "--segment", "oos",
        "--output-dir", str(shard_dir / "batch"),
    ]
    completed = run(command)
    return {
        "index": index,
        "returncode": completed.returncode,
        "manifest": shard_dir / "batch" / "batch_manifest.json",
        "stderr": completed.stderr[-600:],
    }


def merge(manifests: list[Path], output_dir: Path) -> subprocess.CompletedProcess:
    return run(
        [
            sys.executable, "-X", "utf8", "scripts/merge_batch_manifests.py",
            "--shards", *[str(path) for path in manifests],
            "--output-dir", str(output_dir),
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", default=".tmp-shard")
    parser.add_argument("--seed", type=int, default=20261005)
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args(argv)

    work = ROOT / args.work_dir
    shutil.rmtree(work, ignore_errors=True)
    failures: list[str] = []

    print("=== prepare inputs ===")
    inputs = prepare(work, args.seed)
    print(f"  panel={inputs['panel'].name} factors={inputs['factors'].name} "
          f"candidates={len(inputs['computed'])}")

    shard_lists = split_candidates(inputs["candidates"], work, inputs["computed"], SHARD_COUNT)
    for index, path in enumerate(shard_lists):
        rows = pd.read_csv(path, dtype=str, encoding="utf-8")
        print(f"  shard{index}: {len(rows)} factor(s)")

    print(f"\n=== run {SHARD_COUNT} shards in parallel ===")
    with ThreadPoolExecutor(max_workers=SHARD_COUNT) as pool:
        outcomes = list(
            pool.map(lambda pair: validate_shard(inputs, pair[1], work, pair[0]), enumerate(shard_lists))
        )
    manifests: list[Path] = []
    for outcome in outcomes:
        status = "ok" if outcome["returncode"] == 0 and outcome["manifest"].is_file() else "FAILED"
        print(f"  shard{outcome['index']}: {status}")
        if status == "FAILED":
            failures.append(f"shard{outcome['index']} did not produce a manifest")
            print(f"    {outcome['stderr']}")
        else:
            manifests.append(outcome["manifest"])

    if len(manifests) < 2:
        print("\nnot enough shards succeeded to test the merge")
        return 1

    print("\n=== positive: shards merge cleanly ===")
    merged_dir = work / "merged"
    result = merge(manifests, merged_dir)
    if result.returncode != 0:
        failures.append(f"merge refused clean shards: {result.stdout.strip()[:300]}")
        print(f"  FAILED to merge clean shards (exit {result.returncode})")
        print(f"  {result.stdout.strip()[:400]}")
    else:
        merged = json.loads((merged_dir / "batch_manifest.json").read_text(encoding="utf-8"))
        shard_entries: list[dict] = []
        for path in manifests:
            shard_entries.extend(json.loads(path.read_text(encoding="utf-8"))["results"])
        shard_ids = {entry["factor_id"] for entry in shard_entries}
        merged_ids = {entry["factor_id"] for entry in merged["results"]}
        print(f"  merged {merged['shard_count']} shards, {merged['candidate_count']} candidates")
        print(f"  counts: {merged['counts']}")

        if merged_ids != shard_ids:
            failures.append(
                f"merged factor set differs from the union of shards "
                f"(missing {sorted(shard_ids - merged_ids)}, extra {sorted(merged_ids - shard_ids)})"
            )
        if merged["candidate_count"] != len(shard_ids):
            failures.append(
                f"merged candidate_count {merged['candidate_count']} != union size {len(shard_ids)}"
            )
        expected_validated = sum(
            1 for entry in shard_entries if entry.get("status") == "validated"
        )
        if merged["counts"].get("validated") != expected_validated:
            failures.append(
                f"merged validated count {merged['counts'].get('validated')} != "
                f"sum of shards {expected_validated}"
            )
        if not failures:
            print("  OK: per-factor set and status counts match the union of the shards")

    print("\n=== negative 1: a shard with a different panel must be refused ===")
    tampered = json.loads(manifests[0].read_text(encoding="utf-8"))
    original_hash = tampered["panel_file_sha256"]
    tampered["panel_file_sha256"] = "0" * 64
    tampered_path = work / "tampered_panel_manifest.json"
    tampered_path.write_text(json.dumps(tampered, ensure_ascii=False), encoding="utf-8")
    result = merge([tampered_path, manifests[1]], work / "merged_bad")
    if result.returncode != 2:
        failures.append(
            f"merge accepted a shard with a mismatched panel hash (exit {result.returncode}); "
            "it must refuse with exit 2"
        )
        print(f"  FAILED: expected exit 2, got {result.returncode}")
    else:
        print(f"  OK: refused with exit 2 — {result.stdout.strip().splitlines()[2].strip()[:120]}")
    tampered["panel_file_sha256"] = original_hash

    print("\n=== negative 2: an overlapping factor must be refused ===")
    first = json.loads(manifests[0].read_text(encoding="utf-8"))
    second = json.loads(manifests[1].read_text(encoding="utf-8"))
    if first["results"] and second["results"]:
        duplicated_id = first["results"][0]["factor_id"]
        duplicated = dict(second)
        duplicated["results"] = [dict(first["results"][0]), *second["results"][1:]]
        duplicated_path = work / "overlapping_manifest.json"
        duplicated_path.write_text(json.dumps(duplicated, ensure_ascii=False), encoding="utf-8")
        result = merge([manifests[0], duplicated_path], work / "merged_overlap")
        if result.returncode != 2:
            failures.append(
                f"merge accepted overlapping factor {duplicated_id!r} (exit {result.returncode}); "
                "it must refuse with exit 2"
            )
            print(f"  FAILED: expected exit 2, got {result.returncode}")
        else:
            print(f"  OK: refused overlapping factor {duplicated_id!r} with exit 2")
    else:
        print("  skipped: a shard produced no results")

    print("\n" + "=" * 64)
    if failures:
        print("SHARDED BATCH VERIFICATION FAILED")
        for item in failures:
            print(f"  - {item}")
    else:
        print("SHARDED BATCH VERIFIED: parallel shards merge, and bad shards are refused")
    print("SYNTHETIC DATA ONLY -- this run is not evidence about any factor.")

    if not args.keep and not failures:
        shutil.rmtree(work, ignore_errors=True)
    else:
        print(f"artefacts kept in {work}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
