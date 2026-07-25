"""Submit factor rows to the Factor Lab unified Supabase intake.

This script intentionally does not contain any secret. Configure credentials
with environment variables:

  FACTOR_LAB_SUPABASE_URL
  FACTOR_LAB_SUPABASE_WRITE_KEY

Use a service_role key on a trusted backend/local machine, or an authenticated
user JWT if the project has Supabase Auth enabled. Do not use this from the
GitHub Pages browser frontend.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any


REQUIRED_VALUE_COLUMNS = {"symbol", "trade_date", "value"}


def request_json(
    method: str,
    url: str,
    key: str,
    payload: Any | None = None,
    prefer: str | None = None,
) -> Any:
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
        raise RuntimeError(f"{method} {url} failed: HTTP {exc.code} {detail}") from exc


def chunked(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def read_value_rows(
    csv_path: str,
    batch_id: str,
    factor_family: str,
    factor_name: str,
    source_version: str,
    value_type: str,
) -> list[dict[str, Any]]:
    with open(csv_path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or [])
        missing = REQUIRED_VALUE_COLUMNS - columns
        if missing:
            raise ValueError(f"{csv_path} missing required columns: {', '.join(sorted(missing))}")

        rows = []
        for index, row in enumerate(reader, start=2):
            symbol = (row.get("symbol") or "").strip()
            trade_date = (row.get("trade_date") or "").strip()
            raw_value = (row.get("value") or "").strip()
            if not symbol or not trade_date or raw_value == "":
                raise ValueError(f"{csv_path}:{index} has empty symbol/trade_date/value")
            rows.append(
                {
                    "batch_id": batch_id,
                    "factor_family": factor_family,
                    "factor_name": factor_name,
                    "symbol": symbol,
                    "trade_date": trade_date,
                    "value": float(raw_value),
                    "value_type": (row.get("value_type") or value_type).strip(),
                    "source_version": (row.get("source_version") or source_version).strip(),
                    "raw_payload": {
                        key: value
                        for key, value in row.items()
                        if key not in {"symbol", "trade_date", "value", "value_type", "source_version"}
                        and value not in (None, "")
                    },
                }
            )
    return rows


def read_metric_row(metric_json_path: str | None, batch_id: str, defaults: dict[str, str]) -> dict[str, Any] | None:
    if not metric_json_path:
        return None
    with open(metric_json_path, encoding="utf-8") as handle:
        payload = json.load(handle)
    return {
        "batch_id": batch_id,
        "factor_family": payload.get("factor_family") or defaults["factor_family"],
        "factor_name": payload.get("factor_name") or defaults["factor_name"],
        "library": payload.get("library") or defaults.get("library"),
        "category": payload.get("category"),
        "market": payload.get("market") or defaults.get("market") or "A股",
        "status": payload.get("status") or "candidate",
        "proof_status": payload.get("proof_status"),
        "truth_status": payload.get("truth_status"),
        "overall_status": payload.get("overall_status"),
        "coverage_ratio": payload.get("coverage_ratio"),
        "rank_ic_mean": payload.get("rank_ic_mean"),
        "rank_ic_ir": payload.get("rank_ic_ir"),
        "ic_mean": payload.get("ic_mean"),
        "ic_ir": payload.get("ic_ir"),
        "long_short_mean": payload.get("long_short_mean"),
        "long_short_ir": payload.get("long_short_ir"),
        "turnover": payload.get("turnover"),
        "start_date": payload.get("start_date"),
        "end_date": payload.get("end_date"),
        "metadata": payload.get("metadata") or {},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Submit factor data through the unified Supabase intake.")
    parser.add_argument("--values-csv", required=True, help="CSV with symbol,trade_date,value columns.")
    parser.add_argument("--metrics-json", help="Optional JSON containing IC/IR/coverage metrics.")
    parser.add_argument("--entry-type", required=True, choices=["truth_compare", "research_reproduction", "manual_metric", "legacy_table_import"])
    parser.add_argument("--factor-family", required=True)
    parser.add_argument("--factor-name", required=True)
    parser.add_argument("--library")
    parser.add_argument("--market", default="A股")
    parser.add_argument("--source-name", required=True)
    parser.add_argument("--source-version", default="v1")
    parser.add_argument("--value-type", default="submitted", choices=["truth", "submitted", "reproduced", "research"])
    parser.add_argument("--submitted-by")
    parser.add_argument("--source-uri")
    parser.add_argument("--no-publish", action="store_true", help="Normalize but do not publish to public_dashboard_factors.")
    parser.add_argument("--chunk-size", type=int, default=1000)
    args = parser.parse_args()

    base_url = os.environ.get("FACTOR_LAB_SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("FACTOR_LAB_SUPABASE_WRITE_KEY", "")
    if not base_url or not key:
        print("Missing FACTOR_LAB_SUPABASE_URL or FACTOR_LAB_SUPABASE_WRITE_KEY.", file=sys.stderr)
        return 2

    rest_url = f"{base_url}/rest/v1"
    batch_payload = {
      "entry_type": args.entry_type,
      "factor_family": args.factor_family,
      "factor_name": args.factor_name,
      "library": args.library,
      "market": args.market,
      "source_name": args.source_name,
      "source_version": args.source_version,
      "source_uri": args.source_uri,
      "submitted_by": args.submitted_by,
      "metadata": {"submitted_by_script": "scripts/submit_supabase_unified_factor.py"},
    }
    batch_result = request_json(
        "POST",
        f"{rest_url}/factor_import_batches?select=batch_id",
        key,
        [batch_payload],
        prefer="return=representation",
    )
    batch_id = batch_result[0]["batch_id"]

    value_rows = read_value_rows(
        args.values_csv,
        batch_id,
        args.factor_family,
        args.factor_name,
        args.source_version,
        args.value_type,
    )
    for group in chunked(value_rows, args.chunk_size):
        request_json("POST", f"{rest_url}/factor_values_staging", key, group)

    metric_row = read_metric_row(
        args.metrics_json,
        batch_id,
        {
            "factor_family": args.factor_family,
            "factor_name": args.factor_name,
            "library": args.library,
            "market": args.market,
        },
    )
    if metric_row:
        request_json("POST", f"{rest_url}/factor_metric_staging", key, [metric_row])

    normalize_result = request_json(
        "POST",
        f"{rest_url}/rpc/normalize_factor_import_batch",
        key,
        {"p_batch_id": batch_id, "p_publish": not args.no_publish},
    )
    print(json.dumps(normalize_result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
