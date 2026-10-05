"""Size the degenerate-perturbation problem and check the export writes the variants."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import build_candidate_list as builder  # noqa: E402

MULTIPLIERS = (0.8, 1.2)

factors = json.loads((ROOT / "pages" / "factor-db-dashboard" / "data" / "factors.json").read_text(encoding="utf-8"))["factors"]
rows, _ = builder.build_rows(factors, include_not_runnable=False)
windowed = [r for r in rows if r["window"]]

print(f"windowed candidates: {len(windowed)}")

degenerate = []
partial = []
for row in windowed:
    base = int(row["window"])
    windows = [max(1, int(round(base * m))) for m in MULTIPLIERS]
    if all(w == base for w in windows):
        degenerate.append((row["factor_id"], base, windows))
    elif any(w == base for w in windows):
        partial.append((row["factor_id"], base, windows))

print(f"\nvacuous perturbation (EVERY variant window == base): {len(degenerate)}")
for factor_id, base, windows in degenerate[:20]:
    print(f"  {factor_id:<24} base={base} variants={windows}")

print(f"\npartially degenerate (SOME variant window == base): {len(partial)}")
for factor_id, base, windows in partial[:20]:
    print(f"  {factor_id:<24} base={base} variants={windows}")

if windowed:
    smallest = sorted({int(r["window"]) for r in windowed})[:6]
    print(f"\nsmallest base windows present: {smallest}")

# Does the export script emit a variant entry when the window coincides?
print("\n--- how the factor export builds variant names ---")
patterns = ("build_factor", "export_factor", "factor_values", "shard")
candidates = []
for path in sorted((ROOT / "scripts").glob("*.py")):
    text = path.read_text(encoding="utf-8")
    if "|window=" in text or "perturbation_factor_name" in text or "multipliers" in text:
        candidates.append(path)
for path in candidates:
    print(f"  {path.relative_to(ROOT)}")
    text = path.read_text(encoding="utf-8")
    for index, line in enumerate(text.splitlines(), start=1):
        if re.search(r"multiplier|window=|perturbation", line):
            print(f"      {index:>4}: {line.strip()[:100]}")
