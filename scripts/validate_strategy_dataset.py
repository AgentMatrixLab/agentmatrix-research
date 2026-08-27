from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from research_core.strategy_operations.dataset_validation import validate_dataset


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate an immutable strategy dataset")
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--skip-hashes", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = validate_dataset(args.root, verify_hashes=not args.skip_hashes)
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    print(serialized)
    return 0 if report["status"] == "ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
