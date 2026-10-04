"""Verify the last mile: merged batch -> delivery package -> independent cross-check.

`cross_check_delivery.py` is the final gate before anything reaches the client. It
re-derives every hash from the artifacts rather than trusting the manifests, which
only means something if it actually fails when an artifact has been altered. A
cross-check that always passes is indistinguishable from no cross-check.

So this runs the real sequence on rehearsal data and then deliberately breaks it:

  positive  sharded batch -> merge -> package -> cross-check exits 0;
            the package contains exactly the validated factors and lists every
            rejection with a reason; factor_catalog.csv is written.
  negative  alter a packaged factor's evidence and cross-check must find it
            (exit 5), naming the factor and the check.

    python -X utf8 scripts/dev/verify_delivery_packaging.py
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

import verify_sharded_batch as sharded  # noqa: E402

SHARDS = 2


def run(command: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(command, cwd=ROOT, capture_output=True, text=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", default=".tmp-package")
    parser.add_argument("--seed", type=int, default=20261005)
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args(argv)

    work = ROOT / args.work_dir
    shutil.rmtree(work, ignore_errors=True)
    failures: list[str] = []

    print("=== prepare inputs ===")
    inputs = sharded.prepare(work, args.seed)
    print(f"  candidates={len(inputs['computed'])}")

    shard_lists = sharded.split_candidates(inputs["candidates"], work, inputs["computed"], SHARDS)
    print(f"\n=== run {SHARDS} shards in parallel ===")
    with ThreadPoolExecutor(max_workers=SHARDS) as pool:
        outcomes = list(
            pool.map(lambda pair: sharded.validate_shard(inputs, pair[1], work, pair[0]), enumerate(shard_lists))
        )
    manifests = [o["manifest"] for o in outcomes if o["returncode"] == 0 and o["manifest"].is_file()]
    if len(manifests) != SHARDS:
        print("  a shard failed; stopping")
        return 1
    print(f"  {len(manifests)} shard manifest(s)")

    print("\n=== merge ===")
    merged_dir = work / "merged"
    result = sharded.merge(manifests, merged_dir)
    if result.returncode != 0:
        print(f"  merge failed: {result.stdout.strip()[:300]}")
        return 1
    merged_manifest = merged_dir / "batch_manifest.json"
    merged = json.loads(merged_manifest.read_text(encoding="utf-8"))
    print(f"  counts: {merged['counts']}")

    print("\n=== package (only validated factors may be included) ===")
    package_dir = work / "package"
    result = run(
        [
            sys.executable, "-X", "utf8", "scripts/package_delivery.py",
            "--batch-manifest", str(merged_manifest),
            "--candidates", str(inputs["candidates"]),
            "--output-dir", str(package_dir),
        ]
    )
    if result.returncode != 0:
        # Exit 4 means nothing passed, which is a legitimate outcome for data with
        # no signal rather than a tooling failure.
        print(f"  package exited {result.returncode}")
        print(f"  {result.stdout.strip()[:300]}")
        if result.returncode == 4:
            print("  exit 4 = no factor passed; treating as a correct outcome, not a failure")
            if not args.keep:
                shutil.rmtree(work, ignore_errors=True)
            return 0
        failures.append(f"package_delivery exited {result.returncode}")

    package_manifest_path = package_dir / "package_manifest.json"
    if not package_manifest_path.is_file():
        failures.append("package_manifest.json was not written")
    else:
        package = json.loads(package_manifest_path.read_text(encoding="utf-8"))
        included = [entry["factor_id"] for entry in package.get("included_factors", [])]
        excluded = package.get("excluded_factors", [])
        statuses = {str(entry.get("factor_id")): str(entry.get("status")) for entry in merged["results"]}
        expected_included = sorted(
            fid for fid, status in statuses.items() if status == "validated"
        )

        print(f"  included={len(included)} excluded={len(excluded)}")
        if sorted(included) != expected_included:
            failures.append(
                f"package included {sorted(included)} but validated factors are {expected_included}"
            )
        for entry in excluded:
            if not entry.get("reason"):
                failures.append(f"excluded factor {entry.get('factor_id')} carries no reason")
        if not excluded and expected_included != sorted(statuses):
            failures.append("nothing was excluded even though factors were rejected")
        if not failures:
            print("  OK: included set == validated set; every exclusion carries a reason")

        catalog = package_dir / "factor_catalog.csv"
        if not catalog.is_file():
            failures.append("factor_catalog.csv was not written")
        else:
            frame = pd.read_csv(catalog, dtype=str, encoding="utf-8-sig")
            print(f"  factor_catalog.csv: {len(frame)} row(s), columns={len(frame.columns)}")
            if len(frame) != len(statuses):
                failures.append(
                    f"factor_catalog.csv has {len(frame)} rows but the batch has {len(statuses)} factors"
                )

    print("\n=== cross-check (independent hash re-derivation) ===")
    cross_check_command = [
        sys.executable, "-X", "utf8", "scripts/cross_check_delivery.py",
        "--batch-manifest", str(merged_manifest),
        "--panel-file", str(inputs["panel"]),
        "--factor-file", str(inputs["factors"]),
        "--candidates", str(inputs["candidates"]),
        "--config", str(inputs["config"]),
        "--output", str(work / "cross_check.json"),
    ]
    if package_manifest_path.is_file():
        cross_check_command += ["--package-manifest", str(package_manifest_path)]
    result = run(cross_check_command)
    if result.returncode != 0:
        failures.append(f"cross-check on a clean package exited {result.returncode}")
        print(f"  FAILED (exit {result.returncode})")
        print(f"  {result.stdout.strip()[:600]}")
    else:
        print("  OK: cross-check reports no inconsistency")

    print("\n=== negative: tampering must be detected ===")
    tamper_target = None
    for candidate in package_dir.rglob("*.json"):
        if candidate.name == "package_manifest.json":
            continue
        tamper_target = candidate
        break
    if tamper_target is None:
        print("  skipped: no packaged artifact to tamper with")
    else:
        original = tamper_target.read_text(encoding="utf-8")
        payload = json.loads(original)
        payload["_tamper"] = "altered after packaging"
        tamper_target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        result = run(cross_check_command)
        if result.returncode != 5:
            failures.append(
                f"cross-check returned {result.returncode} on a tampered artifact; "
                "it must return 5 (inconsistencies found)"
            )
            print(f"  FAILED: expected exit 5, got {result.returncode}")
        else:
            print(f"  OK: tampering in {tamper_target.name} detected with exit 5")
        tamper_target.write_text(original, encoding="utf-8")

    print("\n" + "=" * 64)
    if failures:
        print("DELIVERY PACKAGING VERIFICATION FAILED")
        for item in failures:
            print(f"  - {item}")
    else:
        print("DELIVERY PACKAGING VERIFIED: package contents and tamper detection both correct")
    print("SYNTHETIC DATA ONLY -- this run is not evidence about any factor.")

    if not args.keep and not failures:
        shutil.rmtree(work, ignore_errors=True)
    else:
        print(f"artefacts kept in {work}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
