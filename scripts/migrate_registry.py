"""Migrate factor registry from single JSON to per-ID files.

Usage: python scripts/migrate_registry.py <registry.json> <output_dir>
"""
import json, os, sys
from pathlib import Path

def migrate(json_path: str, output_dir: str):
    with open(json_path) as f:
        registry = json.load(f)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    count = 0
    for factor_id, info in registry.items():
        file_path = out / f"{factor_id}.json"
        with open(file_path, "w") as f:
            json.dump(info, f, indent=2, ensure_ascii=False)
        count += 1
    index = {fid: str(out / f"{fid}.json") for fid in registry}
    with open(out / "_index.json", "w") as f:
        json.dump(index, f, indent=2)
    print(f"Migrated {count} factors to {output_dir}/")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python scripts/migrate_registry.py <registry.json> <output_dir>")
        print("No registry file provided. Migration targets per-ID JSON files for git diff compatibility.")
        sys.exit(0)
    migrate(sys.argv[1], sys.argv[2])
