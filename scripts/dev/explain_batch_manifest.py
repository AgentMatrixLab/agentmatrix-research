"""Explain a batch manifest: counts, and the first few errors with reasons."""
from __future__ import annotations

import json
import sys
from pathlib import Path

path = Path(sys.argv[1] if len(sys.argv) > 1 else ".tmp-catalog-batch/batch/batch_manifest.json")
payload = json.loads(path.read_text(encoding="utf-8"))

print(f"keys: {list(payload)}")
for key in ("counts", "validated_effective_alpha", "validated_risk_exposure", "shard_count"):
    if key in payload:
        print(f"  {key}: {payload[key]}")

results = payload.get("results") or []
print(f"\nresults: {len(results)}")
statuses: dict[str, int] = {}
for entry in results:
    statuses[entry.get("status")] = statuses.get(entry.get("status"), 0) + 1
print(f"  statuses: {statuses}")

errors = [entry for entry in results if entry.get("status") == "error"]
print(f"\nerrors: {len(errors)}")
for entry in errors[:8]:
    print(f"  {entry.get('factor_id')}")
    print(f"      {str(entry.get('reason'))[:200]}")
    extra = entry.get("error") or entry.get("exception")
    if extra:
        print(f"      {str(extra)[:200]}")

for key in ("errors", "error", "needs_human", "rejected", "validated"):
    value = payload.get(key)
    if isinstance(value, list) and value:
        print(f"\n{key} ({len(value)}): {value[:8]}")

first = results[0] if results else None
if first:
    print(f"\nfirst entry keys: {list(first)}")
    print(json.dumps(first, ensure_ascii=False, indent=2)[:900])
