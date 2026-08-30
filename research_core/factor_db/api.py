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
import os
import sys
from pathlib import Path

from flask import Blueprint, jsonify, request, send_file

from research_core.factor_db.metadata import get_factor, get_stats, list_factors
from research_core.factor_db.lifecycle_service import (
    LifecycleDataError,
    evidence_feed,
    factor_detail,
    factor_rows,
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


def _send_export(payload: dict):
    import io

    return send_file(
        io.BytesIO(payload["content"]),
        mimetype=payload["mime"],
        as_attachment=True,
        download_name=payload["filename"],
    )


@factor_db_bp.errorhandler(FactorDataError)
def _handle_factor_data_error(exc: FactorDataError):
    return jsonify({"error": str(exc), "status_code": exc.status_code}), exc.status_code


@factor_db_bp.errorhandler(LifecycleDataError)
def _handle_lifecycle_data_error(exc: LifecycleDataError):
    return jsonify({"error": str(exc)}), 425


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
    bins_raw = request.args.get("bins")
    return jsonify(
        factor_distribution(factor_id, demo=demo, bins=int(bins_raw) if bins_raw else 30)
    )


@factor_db_bp.get("/factors/<path:factor_id>/export")
def factor_export_endpoint(factor_id: str):
    payload = export_factor_data(
        factor_id,
        fmt=request.args.get("format", "csv"),
        scope=request.args.get("scope", "values"),
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
    return jsonify(quant_api_status(check_remote=check_remote))


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


def create_app() -> "Flask":
    from flask import Flask
    from flask_cors import CORS

    app = Flask(__name__)
    CORS(app, resources={r"/api/*": {"origins": "*"}})
    app.register_blueprint(factor_db_bp)
    _register_frontend(app)

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
