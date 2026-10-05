"""Rebuild factor values for the factors that passed the frozen gates.

Why this exists: each shard deletes its factor file when it finishes, so at merge
time there are no values left. The robustness layer needs values, and FDR is a
batch-level statistic that must see every factor's p-value at once, so it cannot be
computed per shard either.

The resolution is that the badge is only ever reported for factors that are being
delivered, so only those values need rebuilding -- roughly 60% of the candidates,
in one pass, after the frozen-gate results are already known.

    python scripts/rebuild_passing_factors.py \
        --batch-manifest <merged>/batch_manifest.json \
        --candidates <candidate_list.csv> \
        --panel-file <validation_panel.parquet> \
        --config configs/validation_gates.yaml \
        --output-dir <dir>

Writes <dir>/candidates.csv and <dir>/factor_values.parquet, then prints the
supplement command to run next. It does not run the supplement itself, because
that step is slow and worth watching.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PYTHON = sys.executable


def passing_factor_ids(manifest_path: Path) -> list[str]:
    """Factors with status validated and no failed gates.

    Matches how the delivery manifest decides inclusion: a factor that failed any
    frozen gate is not delivered, so it needs no badge.
    """
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    results = payload.get("results")
    if not isinstance(results, list):
        raise SystemExit(f"{manifest_path} has no results list")
    passed: list[str] = []
    for entry in results:
        if entry.get("status") != "validated":
            continue
        if entry.get("failed_gates"):
            continue
        factor_id = str(entry.get("factor_id", "")).strip()
        if factor_id:
            passed.append(factor_id)
    return passed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--batch-manifest", required=True)
    parser.add_argument("--candidates", required=True)
    parser.add_argument("--panel-file", required=True)
    parser.add_argument("--config", default="configs/validation_gates.yaml")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--emit-start", default="2020-01-02")
    parser.add_argument("--skip-build", action="store_true", help="only write the filtered candidate list")
    args = parser.parse_args(argv)

    manifest = Path(args.batch_manifest)
    if not manifest.is_file():
        raise SystemExit(f"merged manifest not found: {manifest}")

    passed = passing_factor_ids(manifest)
    if not passed:
        raise SystemExit(
            "no factor passed every frozen gate; nothing to rebuild. "
            "That is a result, not an error -- do not widen the gates to change it."
        )
    print(f"passing factors in the merged manifest: {len(passed)}")

    with Path(args.candidates).open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    fieldnames = list(rows[0])
    wanted = set(passed)
    subset = [row for row in rows if row["factor_id"] in wanted]
    missing = sorted(wanted - {row["factor_id"] for row in subset})
    if missing:
        print(f"  WARNING: {len(missing)} passing factor(s) are not in the candidate list:")
        for factor_id in missing[:5]:
            print(f"    {factor_id}")
    print(f"candidate rows: {len(rows)} -> {len(subset)}")

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    subset_path = out_dir / "candidates.csv"
    with subset_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(subset)
    print(f"wrote {subset_path}")

    if args.skip_build:
        return 0

    factor_path = out_dir / "factor_values.parquet"
    command = [
        PYTHON, "-X", "utf8", "-u", str(ROOT / "scripts" / "build_factor_values.py"),
        "--candidates", str(subset_path),
        "--panel-file", args.panel_file,
        "--config", args.config,
        "--output", str(factor_path),
        "--report", str(out_dir / "build_report.json"),
        "--emit-start", args.emit_start,
    ]
    print(f"\nrunning build_factor_values for {len(subset)} factors ...")
    completed = subprocess.run(command, cwd=ROOT)
    if completed.returncode != 0:
        raise SystemExit("build_factor_values failed; see its output above")

    print(f"\nwrote {factor_path}")
    print("\nNEXT -- run the robustness layer against these values:")
    print(
        "  python -X utf8 scripts/run_robustness_supplement.py "
        f"--factor-file {factor_path} --panel-file {args.panel_file} --q 0.05 "
        f"--out {out_dir / 'supplementary_report.json'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
