"""Diagnose the catalogue-batch rehearsal: missing result and unmeasured perturbation."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "dev"))

import build_candidate_list as builder  # noqa: E402
from research_core.factor_lab.deterministic_validation import safe_factor_directory_name  # noqa: E402

work = Path(sys.argv[1] if len(sys.argv) > 1 else ".tmp-catalog-batch")

candidates = pd.read_csv(work / "candidate_list.csv", dtype=str, keep_default_na=False)
candidate_ids = list(candidates["factor_id"])
print(f"candidates: {len(candidate_ids)}")

runs = work / "validation_runs"
dirs = sorted(p.name for p in runs.iterdir() if p.is_dir())
print(f"run directories: {len(dirs)}")

expected = {safe_factor_directory_name(fid): fid for fid in candidate_ids}
actual = set(dirs)
missing = sorted(set(expected) - actual)
print(f"\nmissing run directories ({len(missing)}):")
for name in missing:
    print(f"  {expected[name]}  -> expected dir {name}")
    matches = list(runs.glob(f"{name}*"))
    print(f"      glob matches: {[m.name for m in matches]}")

extra = sorted(actual - set(expected))
if extra:
    print(f"\nunexpected directories: {extra}")

# Which factors declared which window, and do the multipliers degenerate?
config = json.loads((work / "rehearsal_config.json").read_text(encoding="utf-8")) if (work / "rehearsal_config.json").is_file() else None
multipliers = None
if config:
    multipliers = config.get("perturbation", {}).get("multipliers")
print(f"\nperturbation multipliers from the config: {multipliers}")

if multipliers:
    print("\ncandidates whose perturbation windows coincide with the base:")
    degenerate = []
    for _, row in candidates.iterrows():
        base = int(row["window"])
        windows = [max(1, int(round(base * float(m)))) for m in multipliers]
        if all(w == base for w in windows):
            degenerate.append((row["factor_id"], base, windows))
    print(f"  count: {len(degenerate)}")
    for factor_id, base, windows in degenerate[:10]:
        print(f"    {factor_id}  base={base} variants={windows}")

    print("\ncandidates with any coinciding variant window:")
    any_coincide = []
    for _, row in candidates.iterrows():
        base = int(row["window"])
        windows = [max(1, int(round(base * float(m)))) for m in multipliers]
        if any(w == base for w in windows):
            any_coincide.append((row["factor_id"], base, windows))
    print(f"  count: {len(any_coincide)}")
    for factor_id, base, windows in any_coincide[:10]:
        print(f"    {factor_id}  base={base} variants={windows}")

# How many catalog candidates overall have a degenerate perturbation?
factors = json.loads((ROOT / "pages" / "factor-db-dashboard" / "data" / "factors.json").read_text(encoding="utf-8"))["factors"]
rows, _ = builder.build_rows(factors, include_not_runnable=False)
windowed = [r for r in rows if r["window"]]
if multipliers:
    degenerate_all = [
        r for r in windowed
        if all(max(1, int(round(int(r["window"]) * float(m)))) == int(r["window"]) for m in multipliers)
    ]
    print(f"\nACROSS THE WHOLE CATALOG: {len(degenerate_all)}/{len(windowed)} windowed candidates "
          f"have a vacuous perturbation (every variant window equals the base)")
