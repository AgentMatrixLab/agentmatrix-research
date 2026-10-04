"""Inspect a produced delivery manifest: header, delivered rows, and summary."""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

path = Path(sys.argv[1] if len(sys.argv) > 1 else ".tmp-rehearsal/delivery_manifest.csv")
summary_path = path.with_suffix(".summary.json")

with path.open(encoding="utf-8-sig", newline="") as handle:
    rows = list(csv.DictReader(handle))

print(f"rows: {len(rows)}")
print(f"columns ({len(rows[0])}): {list(rows[0])}")
print()
delivered = [row for row in rows if row["in_delivery_package"] == "true"]
print(f"delivered: {len(delivered)}")
for row in delivered:
    print(
        f"  {row['factor_id']:<12} tier={row['tier']} composite={row['composite']} "
        f"fdr={row['fdr_accepted']} cluster={row['cluster_id']} role={row['cluster_role']} "
        f"neutral_retention={row['industry_neutral_retention']}"
    )
print()
not_delivered = [row for row in rows if row["in_delivery_package"] != "true"]
print("why the rest are excluded:")
reasons: dict[str, int] = {}
for row in not_delivered:
    if row["status"] != "validated":
        key = f"failed gates ({row['failed_gates'] or row['status']})"
    elif row["tier"] not in ("S", "A"):
        key = f"tier {row['tier'] or '(unscored)'}"
    elif row["counts_as_alpha"] != "true":
        key = "risk exposure"
    else:
        key = "other"
    reasons[key] = reasons.get(key, 0) + 1
for key, count in sorted(reasons.items(), key=lambda kv: -kv[1]):
    print(f"  x{count:<3} {key}")

if summary_path.is_file():
    print()
    print("summary:", json.dumps(json.loads(summary_path.read_text(encoding="utf-8")), ensure_ascii=False))
