"""Factor DB API：A股因子数据库产品 API 原型。

可独立运行（python -m research_core.factor_db.api --port 8013），
也可作为蓝图挂载到现有 factor_lab_api Flask 应用。

端点总览（前缀 /api/factor-db）：
- GET /stats                              目录统计
- GET /factors                            因子列表（检索/过滤/分页）
- GET /factors/{factor_id}                因子详情（含 LaTeX 公式）
- GET /factors/{factor_id}/values         因子值查询（真实数据，需 token）
- GET /factors/{factor_id}/distribution   分布统计（demo=1 可无 token 演示）
- GET /factors/{factor_id}/export         数据导出（format=csv|xlsx, scope=values|meta）
- GET /dictionary                         数据字典（format=json|csv|xlsx）
- GET /quant-api/status                   数据源状态
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path

from flask import Blueprint, g, jsonify, request, send_file

from research_core.factor_db.metadata import get_factor, get_stats, list_factors
from research_core.factor_db.lifecycle_service import (
    LifecycleDataError,
    evidence_feed,
    factor_detail,
    factor_rows,
    monitor_report,
    overview,
)
from research_core.factor_db.service import (
    FactorDataError,
    export_dictionary,
    export_factor_data,
    factor_distribution,
    factor_values,
    quant_api_status,
)

project_root = Path(__file__).resolve().parents[2]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

factor_db_bp = Blueprint("factor_db", __name__, url_prefix="/api/factor-db")

frontend_root = project_root / "frontend" / "factor-db"
lifecycle_frontend_root = project_root / "frontend" / "lifecycle-dashboard"
_RATE_LIMIT_LOCK = threading.Lock()
_RATE_LIMIT_BUCKETS: dict[str, deque[float]] = defaultdict(deque)


def _send_export(payload: dict):
    import io

    return send_file(
        io.BytesIO(payload["content"]),
        mimetype=payload["mime"],
        as_attachment=True,
        download_name=payload["filename"],
    )


def _csv_env(name: str) -> list[str]:
    raw = os.getenv(name, "")
    return [item.strip() for item in raw.split(",") if item.strip()]


def _factor_db_cors_origins() -> list[str]:
    defaults = [
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:8012",
        "http://localhost:8012",
        "null",
    ]
    public_origin = os.getenv("FACTOR_DB_PUBLIC_ORIGIN") or os.getenv("FACTOR_LAB_PUBLIC_ORIGIN")
    if public_origin:
        defaults.append(public_origin.strip())
    return _csv_env("FACTOR_DB_CORS_ORIGINS") or _csv_env("FACTOR_LAB_CORS_ORIGINS") or defaults


def _configured_api_keys() -> list[str]:
    return _csv_env("FACTOR_DB_API_KEYS") or _csv_env("FACTOR_DB_API_KEY")


def _customer_policies() -> list[dict]:
    raw_json = os.getenv("FACTOR_DB_CUSTOMER_POLICIES_JSON", "").strip()
    policy_path = os.getenv("FACTOR_DB_CUSTOMER_POLICIES_PATH", "").strip()
    payload = None
    if raw_json:
        payload = json.loads(raw_json)
    elif policy_path:
        payload = json.loads(Path(policy_path).read_text(encoding="utf-8"))
    if payload is None:
        return []
    if not isinstance(payload, list):
        return []
    rows: list[dict] = []
    for idx, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            continue
        api_key = str(item.get("api_key", "")).strip()
        if not api_key:
            continue
        customer_id = str(item.get("customer_id") or item.get("name") or f"customer_{idx}").strip()
        rows.append(
            {
                "auth_mode": "customer_policy",
                "api_key": api_key,
                "customer_id": customer_id,
                "customer_name": str(item.get("name") or customer_id).strip(),
                "expires_at": str(item.get("expires_at", "")).strip() or None,
                "allowed_sources": [str(x).strip() for x in (item.get("allowed_sources") or []) if str(x).strip()],
                "allowed_factors": [str(x).strip() for x in (item.get("allowed_factors") or []) if str(x).strip()],
                "allow_export_values": bool(item.get("allow_export_values", False)),
                "rate_limit_count": item.get("rate_limit_count"),
                "rate_limit_window_seconds": item.get("rate_limit_window_seconds"),
            }
        )
    return rows


def _rate_limit_window_seconds() -> int:
    raw = os.getenv("FACTOR_DB_RATE_LIMIT_WINDOW_SECONDS", "60").strip()
    try:
        return max(int(raw), 1)
    except ValueError:
        return 60


def _rate_limit_count() -> int:
    raw = os.getenv("FACTOR_DB_RATE_LIMIT_COUNT", "120").strip()
    try:
        return int(raw)
    except ValueError:
        return 120


def _controlled_endpoint_names() -> list[str]:
    return [
        "values",
        "distribution",
        "export-values",
        "quant-status-remote",
    ]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_timestamp(raw: str | None) -> datetime | None:
    if not raw:
        return None
    value = raw.strip()
    if not value:
        return None
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _client_ip() -> str:
    forwarded = request.headers.get("X-Forwarded-For", "").strip()
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"


def _api_key_fingerprint(api_key: str) -> str:
    import hashlib

    digest = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
    return f"key_{digest[:12]}"


def _audit_log_path() -> Path:
    custom = os.getenv("FACTOR_DB_AUDIT_LOG_PATH", "").strip()
    if custom:
        return Path(custom)
    return project_root / "runtime" / "factor_db" / "audit" / "access.jsonl"


def _write_audit_event(event: dict) -> None:
    path = _audit_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")


def _track_rate_limit(client_id: str, endpoint: str, *, limit: int, window: int) -> None:
    if limit <= 0:
        return
    bucket_key = f"{client_id}:{endpoint}"
    now = time.time()
    with _RATE_LIMIT_LOCK:
        bucket = _RATE_LIMIT_BUCKETS[bucket_key]
        cutoff = now - window
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        if len(bucket) >= limit:
            raise FactorDataError(
                f"受控接口访问过于频繁，请在 {window} 秒后重试",
                status_code=429,
            )
        bucket.append(now)


def _find_principal(api_key: str | None) -> dict | None:
    if not api_key:
        return None
    policies = _customer_policies()
    if policies:
        for policy in policies:
            if policy["api_key"] == api_key:
                return policy
        return None
    if api_key in _configured_api_keys():
        return {
            "auth_mode": "api_key_list",
            "api_key": api_key,
            "customer_id": _api_key_fingerprint(api_key),
            "customer_name": "legacy_api_key",
            "expires_at": None,
            "allowed_sources": [],
            "allowed_factors": [],
            "allow_export_values": True,
            "rate_limit_count": _rate_limit_count(),
            "rate_limit_window_seconds": _rate_limit_window_seconds(),
        }
    return None


def _principal_limit_value(raw: object, fallback: int) -> int:
    try:
        return max(int(raw), 1)
    except (TypeError, ValueError):
        return fallback


def _principal_factor_allowed(principal: dict, factor_id: str | None) -> bool:
    if not factor_id:
        return True
    allowed_factors = principal.get("allowed_factors") or []
    allowed_sources = principal.get("allowed_sources") or []
    if not allowed_factors and not allowed_sources:
        return True
    if factor_id in allowed_factors:
        return True
    source = factor_id.split(":", 1)[0]
    return source in allowed_sources


def _begin_controlled_request(endpoint: str, *, factor_id: str | None = None) -> dict:
    event = {
        "ts": _now_iso(),
        "endpoint": endpoint,
        "factor_id": factor_id,
        "method": request.method,
        "path": request.path,
        "client_ip": _client_ip(),
        "query": {k: v for k, v in request.args.items()},
    }
    policies = _customer_policies()
    keys = _configured_api_keys()
    if not policies and not keys:
        event.update({"auth": "disabled", "outcome": "rejected"})
        g.factor_db_controlled_event = event
        raise FactorDataError(
            "受控接口未启用：请先配置 FACTOR_DB_CUSTOMER_POLICIES_JSON / FACTOR_DB_CUSTOMER_POLICIES_PATH 或 FACTOR_DB_API_KEYS",
            status_code=503,
        )

    provided = _request_api_key()
    principal = _find_principal(provided)
    if principal is None:
        event.update({"auth": "missing_or_invalid", "outcome": "rejected"})
        g.factor_db_controlled_event = event
        raise FactorDataError(
            "该接口需要客户凭证，请通过 Authorization: Bearer <key> 或 X-FactorDB-API-Key 提供 API Key",
            status_code=401,
        )

    expires_at = _parse_timestamp(principal.get("expires_at"))
    if expires_at and datetime.now(timezone.utc) > expires_at:
        event.update(
            {
                "auth": "expired",
                "customer_id": principal["customer_id"],
                "customer_name": principal["customer_name"],
                "auth_mode": principal["auth_mode"],
                "outcome": "rejected",
            }
        )
        g.factor_db_controlled_event = event
        raise FactorDataError("客户凭证已过期，请联系管理员续期", status_code=403)

    if not _principal_factor_allowed(principal, factor_id):
        event.update(
            {
                "auth": "forbidden_factor",
                "customer_id": principal["customer_id"],
                "customer_name": principal["customer_name"],
                "auth_mode": principal["auth_mode"],
                "outcome": "rejected",
            }
        )
        g.factor_db_controlled_event = event
        raise FactorDataError(f"客户无权访问因子 {factor_id}", status_code=403)

    if endpoint == "export-values" and not principal.get("allow_export_values", True):
        event.update(
            {
                "auth": "forbidden_export",
                "customer_id": principal["customer_id"],
                "customer_name": principal["customer_name"],
                "auth_mode": principal["auth_mode"],
                "outcome": "rejected",
            }
        )
        g.factor_db_controlled_event = event
        raise FactorDataError("当前客户策略不允许导出真实因子值", status_code=403)

    client_id = principal["customer_id"]
    limit = _principal_limit_value(principal.get("rate_limit_count"), _rate_limit_count())
    window = _principal_limit_value(principal.get("rate_limit_window_seconds"), _rate_limit_window_seconds())
    event.update(
        {
            "auth": "ok",
            "client_id": client_id,
            "customer_id": principal["customer_id"],
            "customer_name": principal["customer_name"],
            "auth_mode": principal["auth_mode"],
            "expires_at": principal.get("expires_at"),
            "allow_export_values": bool(principal.get("allow_export_values", True)),
            "allowed_sources": principal.get("allowed_sources") or [],
            "allowed_factors": principal.get("allowed_factors") or [],
            "rate_limit_count": limit,
            "rate_limit_window_seconds": window,
        }
    )
    g.factor_db_controlled_event = event
    _track_rate_limit(client_id, endpoint, limit=limit, window=window)
    return event


def _request_api_key() -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
        if token:
            return token
    token = request.headers.get("X-FactorDB-API-Key", "").strip()
    return token or None


def _public_quant_status() -> dict:
    payload = quant_api_status(check_remote=False)
    policies = _customer_policies()
    keys = _configured_api_keys()
    policy_mode = "disabled"
    if policies:
        policy_mode = "customer_policies"
    elif keys:
        policy_mode = "api_key_list"
    return {
        "real_data_enabled": payload["token_configured"],
        "auth_required": bool(policies or keys),
        "controlled_access_enabled": bool(policies or keys),
        "mode": policy_mode,
        "controlled_endpoints": _controlled_endpoint_names(),
        "customer_policy_enabled": bool(policies),
        "customer_policy_count": len(policies),
        "rate_limit_count": _rate_limit_count() if (policies or keys) else 0,
        "rate_limit_window_seconds": _rate_limit_window_seconds() if (policies or keys) else 0,
    }


@factor_db_bp.errorhandler(FactorDataError)
def _handle_factor_data_error(exc: FactorDataError):
    return jsonify({"error": str(exc), "status_code": exc.status_code}), exc.status_code


@factor_db_bp.errorhandler(LifecycleDataError)
def _handle_lifecycle_data_error(exc: LifecycleDataError):
    return jsonify({"error": str(exc)}), 425


@factor_db_bp.after_app_request
def _audit_controlled_response(response):
    event = getattr(g, "factor_db_controlled_event", None)
    if not event:
        return response
    payload = dict(event)
    payload["status_code"] = response.status_code
    payload["outcome"] = "ok" if response.status_code < 400 else payload.get("outcome", "error")
    try:
        _write_audit_event(payload)
    except OSError:
        pass
    return response


# ---------------------------------------------------------------------------
# 生命周期监控端点（面板数据只读）
# ---------------------------------------------------------------------------


@factor_db_bp.get("/lifecycle/overview")
def lifecycle_overview_endpoint():
    return jsonify(overview())


@factor_db_bp.get("/lifecycle/factors")
def lifecycle_factors_endpoint():
    rows = factor_rows()
    state = request.args.get("state") or None
    if state:
        rows = [r for r in rows if r["state"] == state]
    return jsonify({"count": len(rows), "factors": rows})


@factor_db_bp.get("/lifecycle/factors/<path:factor_id>")
def lifecycle_factor_detail_endpoint(factor_id: str):
    return jsonify(factor_detail(factor_id))


@factor_db_bp.get("/lifecycle/evidence")
def lifecycle_evidence_endpoint():
    limit_raw = request.args.get("limit")
    return jsonify(
        {"count_limit": int(limit_raw) if limit_raw else 50, "events": evidence_feed(int(limit_raw) if limit_raw else 50)}
    )


@factor_db_bp.get("/lifecycle/monitor")
def lifecycle_monitor_endpoint():
    """衰减监控 + SLA 通知（先跑 python -m research_core.factor_db.lifecycle_monitor）。"""
    report = monitor_report()
    if report is None:
        return jsonify(
            {
                "available": False,
                "hint": "runtime/lifecycle/monitor_report.json 不存在——先运行 "
                "python -X utf8 -m research_core.factor_db.lifecycle_monitor",
                "notifications": [],
            }
        )
    return jsonify({"available": True, **report})


@factor_db_bp.get("/stats")
def stats_endpoint():
    return jsonify(get_stats())


@factor_db_bp.get("/factors")
def factors_endpoint():
    def _int(name: str) -> int | None:
        raw = request.args.get(name)
        return int(raw) if raw not in (None, "") else None

    rows, total = list_factors(
        category=request.args.get("category") or None,
        subcategory=request.args.get("subcategory") or None,
        source=request.args.get("source") or None,
        search=request.args.get("search") or None,
        limit=_int("limit"),
        offset=_int("offset") or 0,
    )
    return jsonify(
        {
            "count": len(rows),
            "total": total,
            "factors": rows,
        }
    )


@factor_db_bp.get("/factors/<path:factor_id>")
def factor_detail_endpoint(factor_id: str):
    row = get_factor(factor_id)
    if row is None:
        return jsonify({"error": f"未知因子: {factor_id}"}), 404
    return jsonify(row)


@factor_db_bp.get("/factors/<path:factor_id>/values")
def factor_values_endpoint(factor_id: str):
    _begin_controlled_request("values", factor_id=factor_id)
    limit_raw = request.args.get("limit")
    payload = factor_values(
        factor_id,
        symbol=request.args.get("symbol") or None,
        date=request.args.get("date") or None,
        limit=int(limit_raw) if limit_raw not in (None, "") else None,
    )
    return jsonify(payload)


@factor_db_bp.get("/factors/<path:factor_id>/distribution")
def factor_distribution_endpoint(factor_id: str):
    demo = request.args.get("demo") in ("1", "true", "yes")
    if not demo:
        _begin_controlled_request("distribution", factor_id=factor_id)
    bins_raw = request.args.get("bins")
    return jsonify(
        factor_distribution(factor_id, demo=demo, bins=int(bins_raw) if bins_raw else 30)
    )


@factor_db_bp.get("/factors/<path:factor_id>/export")
def factor_export_endpoint(factor_id: str):
    scope = request.args.get("scope", "values")
    if scope != "meta":
        _begin_controlled_request("export-values", factor_id=factor_id)
    payload = export_factor_data(
        factor_id,
        fmt=request.args.get("format", "csv"),
        scope=scope,
        symbol=request.args.get("symbol") or None,
        date=request.args.get("date") or None,
    )
    return _send_export(payload)


@factor_db_bp.get("/dictionary")
def dictionary_endpoint():
    fmt = (request.args.get("format") or "json").lower()
    if fmt == "json":
        from research_core.factor_db.metadata import dictionary_rows

        return jsonify({"count": len(dictionary_rows()), "rows": dictionary_rows()})
    return _send_export(export_dictionary(fmt))


@factor_db_bp.get("/quant-api/status")
def quant_api_status_endpoint():
    check_remote = request.args.get("remote") in ("1", "true", "yes")
    if check_remote:
        _begin_controlled_request("quant-status-remote")
        return jsonify(quant_api_status(check_remote=True))
    return jsonify(_public_quant_status())


def _register_frontend(app):
    @app.get("/factor-db/")
    def factor_db_index():
        return send_file(frontend_root / "index.html")

    @app.get("/factor-db/<path:filename>")
    def factor_db_asset(filename: str):
        target = frontend_root / filename
        if target.is_file():
            return send_file(target)
        return send_file(frontend_root / "index.html")

    @app.get("/lifecycle/")
    def lifecycle_index():
        return send_file(lifecycle_frontend_root / "index.html")

    @app.get("/lifecycle/<path:filename>")
    def lifecycle_asset(filename: str):
        target = lifecycle_frontend_root / filename
        if target.is_file():
            return send_file(target)
        return send_file(lifecycle_frontend_root / "index.html")


def register_factor_db(app) -> None:
    """把 Factor DB API 与静态页面挂载到已有 Flask 应用。

    独立运行与宿主挂载共用同一套注册逻辑，避免两边路由漂移。
    """
    if "factor_db" not in app.blueprints:
        app.register_blueprint(factor_db_bp)
    if "factor_db_index" not in app.view_functions:
        _register_frontend(app)


def create_app() -> "Flask":
    from flask import Flask
    from flask_cors import CORS

    app = Flask(__name__)
    CORS(app, resources={r"/api/*": {"origins": _factor_db_cors_origins()}})
    register_factor_db(app)

    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "service": "factor_db"})

    return app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="A-share Factor DB prototype API server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8013)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args(argv)

    app = create_app()
    print(f"[factor-db] frontend: http://{args.host}:{args.port}/factor-db/")
    print(f"[factor-db] api     : http://{args.host}:{args.port}/api/factor-db/factors")
    token_hint = os.getenv("FACTOR_LAB_QUANT_API_TOKEN") or os.getenv("QUANT_API_TOKEN")
    print(f"[factor-db] token   : {'configured' if token_hint else 'NOT configured (values/distribution need it; use demo=1 for demo)'}")
    app.run(host=args.host, port=args.port, debug=args.debug)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
