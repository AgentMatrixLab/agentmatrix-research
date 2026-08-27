from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ENTRY_CONFIG = {
    "truth-compare": {
        "task_type": "truth_compare",
        "skill_name": "truth_compare_v1",
        "endpoint": "/api/agents/factor-lab/intake/truth-compare",
        "required_files": ["factor_values.csv"],
        "instruction": (
            "Run the Factor Lab truth-compare intake path. Compare the submitted "
            "factor_values.csv with the library standard truth; do not promote directly."
        ),
    },
    "research-reproduction": {
        "task_type": "research_reproduction",
        "skill_name": "research_reproduction_v1",
        "endpoint": "/api/agents/factor-lab/intake/research-reproduction",
        "required_files": ["code.py", "experiment_data.csv", "paper.pdf", "research_report.pdf"],
        "instruction": (
            "Run the Factor Lab research-reproduction intake path. Reconstruct a runnable "
            "candidate factor from the research package; standard truth is optional diagnostics."
        ),
    },
}


def _load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _json_load(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} is invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _file_item(root: Path, path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "name": path.name,
        "relative_path": str(path.relative_to(root.parent)).replace("\\", "/"),
        "size": stat.st_size,
        "type": mimetypes.guess_type(str(path))[0] or "",
        "last_modified": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
    }


def _validate_package(entry: str, submission_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if entry not in ENTRY_CONFIG:
        raise ValueError(f"unknown entry: {entry}")
    if not submission_dir.is_dir():
        raise ValueError(f"submission path must be a directory: {submission_dir}")

    manifest_path = submission_dir / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError("submission package is missing manifest.json")
    manifest = _json_load(manifest_path)

    config = ENTRY_CONFIG[entry]
    missing = [name for name in config["required_files"] if not (submission_dir / name).is_file()]
    if missing:
        raise ValueError(f"{entry} package is missing required files: {', '.join(missing)}")

    declared_type = manifest.get("task_type")
    if declared_type and declared_type != config["task_type"]:
        raise ValueError(f"manifest.task_type must be {config['task_type']}, got {declared_type}")

    if entry == "truth-compare":
        for field in ("factor_family", "factor_name"):
            if not manifest.get(field):
                raise ValueError(f"truth-compare manifest must include {field}")

    allowed = {"manifest.json", *config["required_files"], "truth_values.csv", "truth_values.parquet"}
    files = [
        _file_item(submission_dir, child)
        for child in sorted(submission_dir.iterdir())
        if child.is_file() and (child.name in allowed or child.parent.name in {"optional", "references"})
    ]
    return manifest, files


def _build_payload(entry: str, submission_dir: Path) -> dict[str, Any]:
    manifest, files = _validate_package(entry, submission_dir)
    config = ENTRY_CONFIG[entry]
    now = datetime.now(timezone.utc).isoformat()
    package_name = str(manifest.get("package_name") or submission_dir.name)
    payload = {
        "schema_version": "factor_intake_request_v1",
        "task_type": config["task_type"],
        "skill_name": config["skill_name"],
        "factor_family": manifest.get("factor_family"),
        "factor_name": manifest.get("factor_name"),
        "instruction": manifest.get("instruction") or config["instruction"],
        "package": {
            "input_mode": "folder",
            "package_name": package_name,
            "required_files": config["required_files"],
            "files": files,
        },
        "files": files,
        "namespace": manifest.get("namespace") or "quarantine",
        "data_source": manifest.get("data_source") or "quant_api",
        "requires_quant_api": bool(manifest.get("requires_quant_api", True)),
        "human_policy": {
            "interactive_questions": False,
            "human_only_final_approval": True,
        },
        "requested_at": manifest.get("created_at") or now,
        "submitter": manifest.get("submitter"),
        "submission_notes": manifest.get("notes") or [],
    }
    return {key: value for key, value in payload.items() if value is not None}


def _api_host(explicit: str | None) -> str:
    _load_env_file(Path(".env.local"))
    _load_env_file(Path(".env"))
    host = (
        explicit
        or os.environ.get("FACTOR_LAB_API_HOST")
        or os.environ.get("FACTOR_LAB_BACKEND_URL")
        or "http://127.0.0.1:8012"
    )
    return host.rstrip("/")


def _post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(
        url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            text = response.read().decode("utf-8")
            return json.loads(text) if text else {}
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Factor Lab API HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Factor Lab API request failed: {exc}") from exc


def submit_intake(entry: str, submission_dir: Path, *, api: str | None, dry_run: bool) -> dict[str, Any]:
    payload = _build_payload(entry, submission_dir)
    config = ENTRY_CONFIG[entry]
    result: dict[str, Any] = {
        "dry_run": dry_run,
        "entry": entry,
        "task_type": payload["task_type"],
        "skill_name": payload["skill_name"],
        "package_name": payload["package"]["package_name"],
        "files": [item["name"] for item in payload["files"]],
    }
    if dry_run:
        result["payload"] = payload
        return result
    endpoint = f"{_api_host(api)}{config['endpoint']}"
    response = _post_json(endpoint, payload)
    result["endpoint"] = endpoint
    result["task_id"] = response.get("task_id")
    result["status"] = response.get("status")
    result["request_path"] = response.get("request_path")
    result["status_path"] = response.get("status_path")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Submit a Factor Lab intake package through one of the two official paths.")
    parser.add_argument("entry", choices=sorted(ENTRY_CONFIG), help="Official intake path to use.")
    parser.add_argument("submission_dir", type=Path, help="Folder containing the intake package.")
    parser.add_argument("--api", help="Factor Lab backend URL. Defaults to FACTOR_LAB_API_HOST or http://127.0.0.1:8012.")
    parser.add_argument("--dry-run", action="store_true", help="Validate and print payload without calling the backend.")
    args = parser.parse_args()

    try:
        result = submit_intake(args.entry, args.submission_dir, api=args.api, dry_run=args.dry_run)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
