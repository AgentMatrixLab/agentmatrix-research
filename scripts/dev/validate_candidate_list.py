"""Validate a generated candidate list against the batch validator's contract."""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from research_core.factor_lab.batch_validation import load_candidate_list  # noqa: E402

path = Path(sys.argv[1] if len(sys.argv) > 1 else ".tmp-candidates.csv")

candidates = load_candidate_list(path)
print(f"loaded {len(candidates)} candidates via load_candidate_list (the real contract check)")

risk = sum(1 for c in candidates if c.risk_exposure)
windowed = sum(1 for c in candidates if c.window is not None)
print(f"  risk exposure : {risk}")
print(f"  with window   : {windowed}")
print(f"  without window: {len(candidates) - windowed}")

frame = pd.read_csv(path, dtype=str, encoding="utf-8-sig", keep_default_na=False)
print(f"  columns       : {list(frame.columns)}")

families = Counter(cid.split(":")[0] for cid in (c.factor_id for c in candidates))
print()
print("by family:")
for name, count in sorted(families.items(), key=lambda kv: -kv[1]):
    print(f"  {name:<10} {count:>4}")

windows = [c.window for c in candidates if c.window is not None]
if windows:
    series = pd.Series(windows)
    print()
    print("window distribution:")
    print(f"  min={series.min()}  median={series.median()}  max={series.max()}")
    print(f"  most common: {series.value_counts().head(6).to_dict()}")

empty_ids = [c.factor_id for c in candidates if not c.factor_id.strip()]
dupes = len(candidates) - len({c.factor_id for c in candidates})
print()
print(f"empty ids: {len(empty_ids)}   duplicates: {dupes}")
print("OK" if not empty_ids and not dupes else "PROBLEM")
