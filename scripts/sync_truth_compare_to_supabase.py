"""把本地真值对照 run 同步到 Supabase（需要 service key）。"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRUTH_RUNS = ROOT / "runtime" / "factor_lab" / "truth_compare"


def request_json(method: str, url: str, key: str, payload=None, prefer: str | None = None):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            text = resp.read().decode("utf-8")
            return json.loads(text) if text else None
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} -> HTTP {exc.code}: {detail}") from exc


def sync_run(run_dir: Path, rest_url: str, key: str) -> dict:
    payload_path = run_dir / "supabase_sync_payload.json"
    marker = run_dir / "_synced.json"
    if not payload_path.exists():
        return {"run": run_dir.name, "synced": False, "reason": "no payload"}
    if marker.exists():
        return {"run": run_dir.name, "synced": False, "reason": "already synced"}

    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    tables = payload["tables"]

    request_json(
        "POST", f"{rest_url}/factor_truth_comparisons", key,
        [tables["factor_truth_comparisons"]],
        prefer="resolution=ignore-duplicates,return=minimal",
    )
    request_json(
        "POST", f"{rest_url}/public_dashboard_factors", key,
        [tables["public_dashboard_factors"]],
        prefer="resolution=merge-duplicates,return=minimal",
    )

    marker.write_text(
        json.dumps({"synced_at": datetime.now(timezone.utc).isoformat()}, indent=2),
        encoding="utf-8",
    )
    return {"run": run_dir.name, "synced": True}


def main() -> int:
    parser = argparse.ArgumentParser(description="同步真值对照结果到 Supabase")
    parser.add_argument("--run-dir", help="只同步指定 run 目录；默认同步全部未同步的")
    args = parser.parse_args()

    base_url = os.environ.get("FACTOR_LAB_SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("FACTOR_LAB_SUPABASE_WRITE_KEY", "")
    if not base_url or not key:
        print("缺少 FACTOR_LAB_SUPABASE_URL 或 FACTOR_LAB_SUPABASE_WRITE_KEY，已中止。", file=sys.stderr)
        return 2
    rest_url = f"{base_url}/rest/v1"

    if args.run_dir:
        run_dirs = [Path(args.run_dir)]
    else:
        run_dirs = sorted(p for p in TRUTH_RUNS.glob("truthcmp-*") if p.is_dir())
    if not run_dirs:
        print("没有找到任何 truth_compare run。")
        return 0

    results = []
    for run_dir in run_dirs:
        try:
            results.append(sync_run(run_dir, rest_url, key))
        except RuntimeError as exc:
            results.append({"run": run_dir.name, "synced": False, "reason": str(exc)})

    print(json.dumps(results, ensure_ascii=False, indent=2))
    ok = sum(1 for r in results if r["synced"])
    print(f"已同步 {ok}/{len(results)} 个 run。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())