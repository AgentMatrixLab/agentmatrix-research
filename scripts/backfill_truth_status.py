from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_ROOTS = [
    Path("runtime/factor_lab"),
    Path("frontend/factor-lab-dashboard/data"),
    Path("pages/factor-lab-dashboard/data"),
]

TRUTH_REQUIRED_MARKERS = ("alpha101", "wq101", "gtja191")


def _is_truth_required_factor(payload: dict[str, Any]) -> bool:
    searchable = " ".join(
        str(payload.get(key, "") or "")
        for key in (
            "id",
            "factor_id",
            "factor_name",
            "library",
            "raw_library",
            "factor_family",
            "criteria_source",
        )
    ).lower()
    return any(marker in searchable for marker in TRUTH_REQUIRED_MARKERS)


def _walk_and_backfill(value: Any, *, apply: bool, path: Path, changes: list[dict[str, Any]]) -> bool:
    changed = False
    if isinstance(value, dict):
        if value.get("truth_status") == "not_applicable" and _is_truth_required_factor(value):
            changes.append(
                {
                    "path": str(path),
                    "id": value.get("id") or value.get("factor_id") or value.get("factor_name"),
                    "library": value.get("library") or value.get("raw_library"),
                    "from": "not_applicable",
                    "to": "not_compared",
                }
            )
            if apply:
                value["truth_status"] = "not_compared"
                value["truth_required"] = True
                value["truth_backfill_reason"] = (
                    "registry truth-required factor had truth_status=not_applicable without proof of truth comparison"
                )
                value["truth_backfilled_at"] = datetime.now(timezone.utc).isoformat()
            changed = True
        for child in value.values():
            changed = _walk_and_backfill(child, apply=apply, path=path, changes=changes) or changed
    elif isinstance(value, list):
        for child in value:
            changed = _walk_and_backfill(child, apply=apply, path=path, changes=changes) or changed
    return changed


def _iter_json_files(roots: list[Path]) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        if root.is_file() and root.suffix.lower() == ".json":
            files.append(root)
        elif root.is_dir():
            files.extend(path for path in root.rglob("*.json") if path.is_file())
    return sorted(set(files))


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill truth_status for truth-required historical factors.")
    parser.add_argument("--apply", action="store_true", help="Write changes. Defaults to dry-run.")
    parser.add_argument("roots", nargs="*", type=Path, help="JSON files or directories to scan.")
    args = parser.parse_args()

    roots = args.roots or DEFAULT_ROOTS
    changes: list[dict[str, Any]] = []
    changed_files = 0
    for path in _iter_json_files(roots):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if _walk_and_backfill(payload, apply=args.apply, path=path, changes=changes):
            changed_files += 1
            if args.apply:
                path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(json.dumps({"mode": mode, "changed_files": changed_files, "changes": changes}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
