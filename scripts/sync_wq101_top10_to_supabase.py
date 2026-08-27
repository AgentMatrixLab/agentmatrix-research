from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "pages" / "factor-lab-dashboard" / "data" / "demo-factor-library.json"
DEFAULT_SQL = ROOT / "supabase" / "seed_factor_lab_dashboard_from_local.sql"
DEFAULT_JSON = ROOT / "data" / "factor_lab" / "public_dashboard_factors_from_local.json"
DEFAULT_SUPABASE_URL = "https://wdgflnxymmqfliajreyb.supabase.co"
DEFAULT_TABLE = "public_dashboard_factors"


def _load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _json_literal(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return "'" + text.replace("'", "''") + "'::jsonb"


def _sql_literal(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    return "'" + text.replace("'", "''") + "'"


def _load_factors(source: Path) -> list[dict[str, Any]]:
    data = json.loads(source.read_text(encoding="utf-8-sig"))
    factors = data.get("factors") or []
    if not isinstance(factors, list):
        raise RuntimeError("Source data must contain a factors array")
    return factors


def _select_factors(source: Path, scope: str) -> list[dict[str, Any]]:
    factors = _load_factors(source)
    if scope == "all":
        return factors
    wanted = {f"alpha{i}" for i in range(1, 11)}
    selected = []
    for factor in factors:
        if factor.get("library") == "WQ101" and factor.get("factor_name") in wanted:
            selected.append(factor)
    by_name = {item["factor_name"]: item for item in selected}
    missing = [name for name in [f"alpha{i}" for i in range(1, 11)] if name not in by_name]
    if missing:
        raise RuntimeError(f"Missing WQ101 factors in source data: {', '.join(missing)}")
    return [by_name[f"alpha{i}"] for i in range(1, 11)]


def build_rows(source: Path = DEFAULT_SOURCE, scope: str = "all") -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for factor in _select_factors(source, scope):
        factor_name = str(factor["factor_name"])
        library = str(factor.get("library") or "User Custom")
        factor_id = str(factor.get("id") or factor.get("factor_id") or f"{library}:{factor_name}")
        payload = {
            **factor,
            "id": factor_id,
            "factor_id": factor_id,
            "source": "supabase_public_dashboard_seed",
            "source_id": f"seed/{library.lower()}/{factor_name}",
            "latest_checked_at": now,
        }
        rows.append(
            {
                "factor_id": factor_id,
                "factor_name": factor_name,
                "factor_family": str(factor.get("factor_family") or library.lower()),
                "library": library,
                "category": factor.get("category") or "量价因子",
                "status": factor.get("overall_status") or "registered",
                "proof_status": factor.get("proof_status"),
                "truth_status": factor.get("truth_status"),
                "overall_status": factor.get("overall_status"),
                "coverage_ratio": factor.get("coverage_ratio"),
                "rank_ic_mean": factor.get("rank_ic_mean"),
                "rank_ic_ir": factor.get("rank_ic_ir"),
                "long_short_mean": factor.get("long_short_mean"),
                "truth_exact_match_ratio": factor.get("truth_exact_match_ratio"),
                "truth_max_abs_error": factor.get("truth_max_abs_error"),
                "latest_task_id": factor.get("latest_job_id") or f"seed-{library.lower()}-{factor_name}",
                "latest_checked_at": now,
                "payload": payload,
            }
        )
    return rows


def write_outputs(rows: list[dict[str, Any]], json_path: Path, sql_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    sql_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    columns = [
        "factor_id",
        "factor_name",
        "factor_family",
        "library",
        "category",
        "status",
        "proof_status",
        "truth_status",
        "overall_status",
        "coverage_ratio",
        "rank_ic_mean",
        "rank_ic_ir",
        "long_short_mean",
        "truth_exact_match_ratio",
        "truth_max_abs_error",
        "latest_task_id",
        "latest_checked_at",
        "payload",
    ]
    values = []
    for row in rows:
        values.append(
            "("
            + ", ".join(_json_literal(row[col]) if col == "payload" else _sql_literal(row[col]) for col in columns)
            + ")"
        )

    assignments = [
        f"{col} = excluded.{col}"
        for col in columns
        if col not in {"factor_id"}
    ]
    columns_sql = ", ".join(columns)
    values_sql = ",\n  ".join(values)
    assignments_sql = ", ".join(assignments)
    sql = f"""-- Seed WQ101 alpha1-alpha10 into Factor Lab public dashboard.
-- Run this in Supabase SQL Editor if you do not have a backend service key locally.

insert into public.public_dashboard_factors (
  {columns_sql}
) values
  {values_sql}
on conflict (factor_id) do update set
  {assignments_sql},
  updated_at = now();
"""
    sql_path.write_text(sql, encoding="utf-8")


def _supabase_key(explicit: str | None) -> str:
    _load_env_file(ROOT / ".env.local")
    _load_env_file(ROOT / ".env")
    key = (
        explicit
        or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("SUPABASE_SECRET_KEY")
        or os.environ.get("FACTOR_LAB_SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("FACTOR_LAB_SUPABASE_SECRET_KEY")
    )
    if not key:
        raise RuntimeError(
            "No Supabase write key found. Set SUPABASE_SERVICE_ROLE_KEY or SUPABASE_SECRET_KEY, "
            "or run the generated SQL in Supabase SQL Editor."
        )
    return key


def upsert_rows(rows: list[dict[str, Any]], supabase_url: str, table: str, key: str) -> dict[str, Any]:
    endpoint = f"{supabase_url.rstrip('/')}/rest/v1/{quote(table)}?on_conflict=factor_id"
    data = json.dumps(rows, ensure_ascii=False).encode("utf-8")
    request = Request(
        endpoint,
        data=data,
        method="POST",
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Prefer": "resolution=merge-duplicates,return=representation",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            text = response.read().decode("utf-8")
            body = json.loads(text) if text else []
            return {"status": response.status, "rows": len(body), "body": body}
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Supabase HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Supabase request failed: {exc}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed local Factor Lab dashboard factors into the Supabase dashboard table.")
    parser.add_argument(
        "--scope",
        choices=["all", "wq101-top10"],
        default="all",
        help="Export all local dashboard factors or only WQ101 alpha1-alpha10.",
    )
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--json-out", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--sql-out", type=Path, default=DEFAULT_SQL)
    parser.add_argument("--supabase-url", default=os.environ.get("FACTOR_LAB_SUPABASE_URL") or DEFAULT_SUPABASE_URL)
    parser.add_argument("--table", default=os.environ.get("FACTOR_LAB_SUPABASE_FACTOR_TABLE") or DEFAULT_TABLE)
    parser.add_argument("--key", help="Supabase service role or secret key. Do not use the frontend publishable key.")
    parser.add_argument("--write", action="store_true", help="Upsert rows through Supabase REST API.")
    args = parser.parse_args()

    rows = build_rows(args.source, scope=args.scope)
    write_outputs(rows, args.json_out, args.sql_out)
    result: dict[str, Any] = {
        "rows_prepared": len(rows),
        "factor_ids": [row["factor_id"] for row in rows],
        "json_out": str(args.json_out),
        "sql_out": str(args.sql_out),
    }
    if args.write:
        result["upload"] = upsert_rows(rows, args.supabase_url, args.table, _supabase_key(args.key))
    else:
        result["upload"] = "skipped; pass --write with a Supabase service/secret key to upsert"
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
