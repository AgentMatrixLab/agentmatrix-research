"""把 zoo 五库因子字典（表达式 + 解释）同步到 Supabase `zoo_factor_dictionary`。

数据源: runtime/factor_db_zoo_extract.json
- expression: 因子表达式（面板不再展示，仅归档）
- comments:   因子解释（list -> 换行拼接）

两种用法:
1. 有 service_role key（环境变量 FACTOR_LAB_SUPABASE_URL / FACTOR_LAB_SUPABASE_WRITE_KEY）:
   python -X utf8 scripts\\sync_zoo_factor_dictionary_to_supabase.py
   通过 REST upsert 写入。

2. 无 key:
   python -X utf8 scripts\\sync_zoo_factor_dictionary_to_supabase.py --offline
   生成 supabase/seed_zoo_factor_dictionary.sql，交给有 Supabase 权限的同事
   在 SQL Editor 中执行（幂等，可重复执行）。
"""
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
EXTRACT_JSON = ROOT / "runtime" / "factor_db_zoo_extract.json"
SEED_SQL = ROOT / "supabase" / "seed_zoo_factor_dictionary.sql"
MIGRATION_SQL = ROOT / "supabase" / "migrations" / "202608280001_zoo_factor_dictionary.sql"


def load_rows() -> list[dict]:
    if not EXTRACT_JSON.exists():
        raise FileNotFoundError(f"未找到 {EXTRACT_JSON}，请先运行 zoo 提取流程。")
    data = json.loads(EXTRACT_JSON.read_text(encoding="utf-8"))
    rows = []
    for lib, factors in data.items():
        for f in factors:
            comments = f.get("comments") or []
            if isinstance(comments, list):
                comments_text = "\n".join(str(c) for c in comments if str(c).strip())
            else:
                comments_text = str(comments)
            rows.append({
                "library": lib,
                "factor_name": f["name"],
                "expression": (f.get("expr") or "").strip(),
                "comments": comments_text.strip(),
            })
    return rows


def sql_quote(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def generate_seed_sql(rows: list[dict]) -> Path:
    lines = [
        "-- 自动生成: zoo 五库因子字典（表达式 + 解释）",
        f"-- 生成时间: {datetime.now(timezone.utc).isoformat()}",
        "-- 幂等: on conflict (library, factor_name) do update",
        "-- 若表不存在，请先执行 supabase/migrations/202608280001_zoo_factor_dictionary.sql",
        "",
    ]
    for r in rows:
        lines.append(
            "insert into public.zoo_factor_dictionary (library, factor_name, expression, comments) values ("
            f"{sql_quote(r['library'])}, {sql_quote(r['factor_name'])}, "
            f"{sql_quote(r['expression'])}, {sql_quote(r['comments'])}"
            ") on conflict (library, factor_name) do update set "
            "expression = excluded.expression, comments = excluded.comments;"
        )
    SEED_SQL.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return SEED_SQL


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
        with urllib.request.urlopen(req, timeout=120) as resp:
            text = resp.read().decode("utf-8")
            return json.loads(text) if text else None
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} -> HTTP {exc.code}: {detail}") from exc


def upload(rows: list[dict], base_url: str, key: str) -> dict:
    rest_url = f"{base_url.rstrip('/')}/rest/v1"
    # 分批 upsert（每批 200 条）
    batch, total = 200, 0
    for i in range(0, len(rows), batch):
        chunk = rows[i : i + batch]
        request_json(
            "POST", f"{rest_url}/zoo_factor_dictionary", key, chunk,
            prefer="resolution=merge-duplicates,return=minimal",
        )
        total += len(chunk)
        print(f"  已上传 {total}/{len(rows)}")
    return {"synced": total}


def main() -> int:
    parser = argparse.ArgumentParser(description="同步 zoo 因子字典（表达式+解释）到 Supabase")
    parser.add_argument("--offline", action="store_true", help="无 write key 时生成 seed SQL")
    args = parser.parse_args()

    try:
        rows = load_rows()
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    libs = {}
    for r in rows:
        libs[r["library"]] = libs.get(r["library"], 0) + 1
    print(f"共 {len(rows)} 个因子: " + ", ".join(f"{k}({v})" for k, v in sorted(libs.items())))

    base_url = os.environ.get("FACTOR_LAB_SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("FACTOR_LAB_SUPABASE_WRITE_KEY", "")

    if args.offline or not (base_url and key):
        if not args.offline:
            print("未设置 FACTOR_LAB_SUPABASE_URL / FACTOR_LAB_SUPABASE_WRITE_KEY，转入 offline 模式。")
        path = generate_seed_sql(rows)
        print(f"已生成 seed SQL: {path}")
        print("请有 Supabase 权限的同事在 SQL Editor 依次执行:")
        print(f"  1. {MIGRATION_SQL.name}（建表，若尚未执行）")
        print(f"  2. {path.name}（导入数据，幂等）")
        return 0

    try:
        result = upload(rows, base_url, key)
        print(f"同步完成: {result['synced']} 条 upsert 到 zoo_factor_dictionary。")
        return 0
    except RuntimeError as exc:
        print(f"上传失败: {exc}", file=sys.stderr)
        print("可先执行建表 SQL: supabase/migrations/202608280001_zoo_factor_dictionary.sql")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
