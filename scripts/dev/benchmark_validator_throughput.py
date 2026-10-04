"""Measure how long the frozen validator actually takes per factor.

The delivery plan quotes "8 cores, 30-60 minutes for the full batch". That number
was derived analytically from matrix sizes, never measured. With a 300-factor
target and a hard date, a wrong estimate is a schedule failure, so this times the
real `validate-batch` and extrapolates.

It also checks the scaling assumption: the cost per factor should grow roughly
linearly in panel rows. If it grows faster, the full-A panel is a bigger problem
than the estimate says.

    python -X utf8 scripts/dev/benchmark_validator_throughput.py
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "dev"))

import rehearse_full_pipeline as rehearsal  # noqa: E402

#: Real all-A panel: ~5400 codes x ~1900 trading days on the frozen split.
REALISTIC_PANEL_ROWS = 5_400 * 1_900


def timed_batch(work_dir: Path, n_factors: int, n_codes: int, seed: int) -> dict:
    shutil.rmtree(work_dir, ignore_errors=True)
    work_dir.mkdir(parents=True, exist_ok=True)

    rehearsal.N_CODES = n_codes
    panel = rehearsal.build_panel(seed)
    panel_path = rehearsal.write_panel(panel, work_dir)

    table, meta = rehearsal.compute_factors(panel)
    factor_path = rehearsal.write_factor_table(table, meta["declared"], work_dir)
    candidates = rehearsal.write_candidate_list(meta["computed"], work_dir)
    config_path = rehearsal.write_rehearsal_config(work_dir)

    subset = meta["computed"][:n_factors]
    frame = pd.read_csv(candidates, dtype=str, encoding="utf-8")
    frame[frame["factor_id"].isin(subset)].to_csv(candidates, index=False, encoding="utf-8")

    command = [
        sys.executable, "-X", "utf8", "-m", "research_core.factor_lab.cli", "validate-batch",
        "--candidates", str(candidates),
        "--config", str(config_path),
        "--panel-file", str(panel_path),
        "--factor-file", str(factor_path),
        "--segment", "oos",
        "--output-dir", str(work_dir / "batch"),
    ]
    started = time.perf_counter()
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    elapsed = time.perf_counter() - started
    if completed.returncode != 0:
        print(completed.stderr[-2000:])
        raise SystemExit(f"validate-batch failed with {completed.returncode}")

    produced = len(list((work_dir / "validation_runs").glob("*/validation_result.json")))
    return {
        "n_factors": len(subset),
        "n_codes": n_codes,
        "panel_rows": int(len(panel)),
        "factor_rows": int(len(table)),
        "produced": produced,
        "seconds": elapsed,
        "seconds_per_factor": elapsed / max(len(subset), 1),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", default=".tmp-bench")
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args(argv)

    work = ROOT / args.work_dir
    runs = [
        timed_batch(work / "small", n_factors=3, n_codes=30, seed=1),
        timed_batch(work / "large", n_factors=6, n_codes=60, seed=2),
    ]

    print(f"{'panel rows':>12} {'codes':>6} {'factors':>8} {'seconds':>9} {'s/factor':>9}")
    for run in runs:
        print(
            f"{run['panel_rows']:>12,} {run['n_codes']:>6} {run['n_factors']:>8} "
            f"{run['seconds']:>9.1f} {run['seconds_per_factor']:>9.2f}"
        )

    small, large = runs
    row_ratio = large["panel_rows"] / small["panel_rows"]
    cost_ratio = large["seconds_per_factor"] / small["seconds_per_factor"]
    print(
        f"\nscaling: panel grew {row_ratio:.2f}x, cost per factor grew {cost_ratio:.2f}x"
    )

    # The two runs share a calendar and differ only in cross-section width, so the
    # row ratio is entirely a code ratio. Cost per factor barely moved, which means
    # the per-date cross-sectional work is NOT the dominant term -- the fixed
    # per-date overhead across ~3000 trading days is. Projecting linearly on rows
    # (as an earlier version of this script did) overstates the cost by ~50x.
    codes_small, codes_large = small["n_codes"], large["n_codes"]
    cost_small, cost_large = small["seconds_per_factor"], large["seconds_per_factor"]
    per_code = (cost_large - cost_small) / (codes_large - codes_small)
    fixed = cost_small - per_code * codes_small

    realistic_codes = 5_400
    projected_linear_in_codes = fixed + per_code * realistic_codes
    # Floors and ceilings rather than one number: the honest answer is a range,
    # because the code term is extrapolated 90x beyond what was measured.
    lower = cost_large
    upper = max(projected_linear_in_codes, cost_large)

    print(
        f"  fit: ~{fixed:.1f}s fixed per factor + ~{per_code:.4f}s per code "
        f"(extrapolated {realistic_codes / codes_large:.0f}x beyond the measurement)"
    )
    print(f"\nprojection for an all-A panel of ~{realistic_codes:,} codes:")
    print(f"  {'seconds/factor':>16}  {'913 factors, 1 core':>20}  {'8 cores':>10}  {'16 cores':>10}")
    for label, value in (("floor (measured)", lower), ("fit", upper)):
        print(
            f"  {label:>16}  {value:>17.1f}  {value * 913 / 3600:>18.1f}h "
            f"{value * 913 / 8 / 3600:>9.1f}h {value * 913 / 16 / 3600:>9.1f}h"
        )

    print(
        "\nREAD THIS BEFORE PLANNING:\n"
        f"  * the measured floor is {lower:.0f} s/factor on a 3,000-day calendar, which\n"
        "    already puts 913 factors at hours, not minutes;\n"
        "  * the code term is extrapolated far beyond the measurement, so the real\n"
        "    figure must be measured on the server before any schedule is committed;\n"
        "  * shard by factor. scripts/merge_batch_manifests.py already merges shards\n"
        "    with hash checks, so throughput scales with cores almost linearly."
    )

    payload = {
        "runs": runs,
        "fit": {"fixed_seconds_per_factor": fixed, "seconds_per_code": per_code},
        "projection": {"floor": lower, "fit": upper, "codes": realistic_codes},
    }
    (work / "benchmark.json").parent.mkdir(parents=True, exist_ok=True)
    (work / "benchmark.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if not args.keep:
        shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
