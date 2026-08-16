from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from research_core.strategy_operations.readiness import build_readiness_manifest, load_readiness_config


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate daily strategy data readiness")
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--config", type=Path, default=Path("config/data_readiness.json"))
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    manifest = build_readiness_manifest(args.root, load_readiness_config(args.config))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, args.output)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0 if manifest["status"] == "ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
