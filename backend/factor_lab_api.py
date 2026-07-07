from __future__ import annotations

import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from flask import Flask, jsonify, request, send_file, send_from_directory
from flask_cors import CORS


project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


def _load_local_env() -> None:
    for env_path in (project_root / ".env.local", project_root / ".env"):
        if not env_path.is_file():
            continue
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_local_env()

from research_core.factor_lab import (  # noqa: E402
    FactorLabWorkspaceConfig,
    get_alpha101_factor_detail,
    get_factor_lab_job,
    get_factor_lab_overview,
    list_alpha101_factors,
    list_factor_lab_jobs,
    run_factor_set_real_data_job,
    run_alpha101_research_job,
)
from research_core.factor_lab_web import (  # noqa: E402
    build_factor_library_view,
    build_factor_view,
    build_research_analysis_view,
)
from research_core.factor_lab_web.artifact_service import (  # noqa: E402
    list_job_artifacts,
    resolve_artifact_path,
)
from research_core.data_loader.quant_api_client import (  # noqa: E402
    QuantApiClient,
    QuantApiError,
)


app = Flask(__name__)
dashboard_root = project_root / "frontend" / "factor-lab-dashboard"


def _cors_origins() -> list[str]:
    defaults = [
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:8012",
        "http://localhost:8012",
        "https://miao050805-arch.github.io",
        "null",
    ]
    public_origin = os.getenv("FACTOR_LAB_PUBLIC_ORIGIN")
    if public_origin:
        defaults.append(public_origin.strip())
    raw = os.getenv(
        "FACTOR_LAB_CORS_ORIGINS",
        ",".join(defaults),
    )
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


CORS(app, resources={r"/api/*": {"origins": _cors_origins()}})


def _workspace() -> FactorLabWorkspaceConfig:
    return FactorLabWorkspaceConfig()


def _quant_api_client() -> QuantApiClient:
    return QuantApiClient()


def _quant_api_params(*allowed: str) -> dict[str, str]:
    allowed_set = set(allowed)
    return {key: value for key, value in request.args.items() if key in allowed_set and value != ""}


def _quant_api_json(callable_):
    try:
        return jsonify(callable_())
    except QuantApiError as exc:
        status = exc.status_code or 502
        return jsonify(
            {
                "error": str(exc),
                "status_code": exc.status_code,
                "payload": exc.payload,
            }
        ), status


_AGENT_TASK_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _agent_tasks_root(*, create: bool = False) -> Path:
    root = project_root / "runtime" / "factor_lab" / "agent_tasks"
    if create:
        root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def _agent_task_dir(task_id: str, *, create_root: bool = False) -> Path:
    if not _AGENT_TASK_ID_RE.match(task_id):
        raise ValueError("invalid task_id")
    root = _agent_tasks_root(create=create_root)
    path = (root / task_id).resolve()
    if path != root and root not in path.parents:
        raise ValueError("invalid task path")
    return path


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


@app.route("/factor-lab-dashboard/", methods=["GET"])
def factor_lab_dashboard():
    return send_from_directory(dashboard_root, "index.html")


@app.route("/factor-lab-dashboard/<path:filename>", methods=["GET"])
def factor_lab_dashboard_asset(filename: str):
    target = dashboard_root / filename
    if target.is_file():
        return send_from_directory(dashboard_root, filename)
    return send_from_directory(dashboard_root, "index.html")


@app.route("/api/agents/factor-lab/overview", methods=["GET"])
def factor_lab_overview():
    return jsonify(get_factor_lab_overview(_workspace()))


@app.route("/api/agents/factor-lab/factor-library", methods=["GET"])
def factor_lab_factor_library():
    return jsonify(build_factor_library_view(_workspace()))


@app.route("/api/agents/factor-lab/health", methods=["GET"])
def factor_lab_health():
    return jsonify({"status": "ok", "service": "factor_lab", "local_flask": True})


@app.route("/api/agents/factor-lab/quant-api/status", methods=["GET"])
def factor_lab_quant_api_status():
    check_remote = request.args.get("remote") in {"1", "true", "yes"}
    return _quant_api_json(lambda: _quant_api_client().status(check_remote=check_remote))


@app.route("/api/agents/factor-lab/quant-api/sources", methods=["GET"])
def factor_lab_quant_api_sources():
    return _quant_api_json(lambda: _quant_api_client().sources())


@app.route("/api/agents/factor-lab/quant-api/ch", methods=["GET"])
def factor_lab_quant_api_ch_tables():
    return _quant_api_json(lambda: _quant_api_client().ch_tables())


@app.route("/api/agents/factor-lab/quant-api/factor-monthly", methods=["GET"])
def factor_lab_quant_api_factor_monthly():
    params = _quant_api_params("symbol", "date", "factor", "top", "order", "order_by", "limit", "offset", "with_total")
    return _quant_api_json(lambda: _quant_api_client().factor_monthly(params))


@app.route("/api/agents/factor-lab/quant-api/factor-monthly/factors", methods=["GET"])
def factor_lab_quant_api_factor_monthly_factors():
    return _quant_api_json(lambda: _quant_api_client().factor_monthly_factors())


@app.route("/api/agents/factor-lab/quant-api/factor-monthly/dates", methods=["GET"])
def factor_lab_quant_api_factor_monthly_dates():
    return _quant_api_json(lambda: _quant_api_client().factor_monthly_dates())


@app.route("/api/agents/factor-lab/quant-api/factor-monthly/stats", methods=["GET"])
def factor_lab_quant_api_factor_monthly_stats():
    return _quant_api_json(lambda: _quant_api_client().factor_monthly_stats())


@app.route("/api/agents/factor-lab/quant-api/factor-monthly/latest", methods=["GET"])
def factor_lab_quant_api_factor_monthly_latest():
    params = _quant_api_params("factor", "top", "order", "order_by")
    return _quant_api_json(lambda: _quant_api_client().factor_monthly_latest(params))


@app.route("/api/agents/factor-lab/quant-api/factor-ic", methods=["GET"])
def factor_lab_quant_api_factor_ic():
    params = _quant_api_params("symbol", "date", "factor", "top", "order", "order_by", "limit", "offset", "with_total")
    return _quant_api_json(lambda: _quant_api_client().factor_ic(params))


@app.route("/api/agents/factor-lab/quant-api/kline-1d", methods=["GET"])
def factor_lab_quant_api_kline_1d():
    params = _quant_api_params("symbol", "date", "factor", "top", "order", "order_by", "limit", "offset", "with_total")
    return _quant_api_json(lambda: _quant_api_client().kline_1d(params))


def _convert_nan_to_null(obj):
    if isinstance(obj, dict):
        return {k: _convert_nan_to_null(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_convert_nan_to_null(v) for v in obj]
    elif isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    else:
        return obj

@app.route("/api/agents/factor-lab/quant-api/research", methods=["POST"])
def factor_lab_quant_api_research():
    payload = request.get_json(silent=True) or {}
    
    factors = payload.get("factors", ["alpha1", "alpha2", "alpha3"])
    if isinstance(factors, str):
        factors = [f.strip() for f in factors.split(",") if f.strip()]
    
    symbols = payload.get("symbols", ["000001.SZ", "000002.SZ"])
    if isinstance(symbols, str):
        symbols = [s.strip() for s in symbols.split(",") if s.strip()]
    
    start_date = payload.get("start_date", "2023-01-01")
    end_date = payload.get("end_date", "2024-01-01")
    factor_set = payload.get("factor_set", "alpha101")
    
    try:
        from scripts.quant_api_research import run_research
        
        result = run_research(factors, symbols, start_date, end_date, factor_set)
        result_clean = _convert_nan_to_null(result)
        return jsonify(result_clean)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/agents/factor-lab/factors/<path:factor_id>/view", methods=["GET"])
def factor_lab_factor_view(factor_id: str):
    payload = build_factor_view(factor_id, _workspace())
    if payload is None:
        return jsonify({"error": "Factor not found"}), 404
    return jsonify(payload)


@app.route("/api/agents/factor-lab/factors/<path:factor_id>/research-analysis/latest", methods=["GET"])
def factor_lab_factor_research_analysis(factor_id: str):
    return jsonify(build_research_analysis_view(factor_id, _workspace()))


@app.route("/api/agents/factor-lab/alpha101/factors", methods=["GET"])
def factor_lab_alpha101_factors():
    items = list_alpha101_factors(_workspace())
    status = request.args.get("status")
    if status:
        items = [item for item in items if item.get("status") == status]
    return jsonify({"items": items, "total": len(items)})


@app.route("/api/agents/factor-lab/alpha101/factors/<factor_name>", methods=["GET"])
def factor_lab_alpha101_factor_detail(factor_name: str):
    try:
        return jsonify(get_alpha101_factor_detail(factor_name, _workspace()))
    except KeyError:
        return jsonify({"error": "Factor not found"}), 404


@app.route("/api/agents/factor-lab/agent-tasks", methods=["GET"])
def factor_lab_agent_tasks():
    root = _agent_tasks_root()
    if not root.exists():
        return jsonify({"items": [], "total": 0})
    items = []
    for task_dir in sorted((path for path in root.iterdir() if path.is_dir()), reverse=True):
        status_path = task_dir / "status.json"
        request_path = task_dir / "request.json"
        try:
            status_payload = json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() else {}
            request_payload = json.loads(request_path.read_text(encoding="utf-8")) if request_path.exists() else {}
        except json.JSONDecodeError:
            status_payload = {"status": "invalid_json"}
            request_payload = {}
        items.append(
            {
                **request_payload,
                **status_payload,
                "task_id": task_dir.name,
                "request_path": str(request_path),
                "status_path": str(status_path),
            }
        )
    return jsonify({"items": items, "total": len(items)})


@app.route("/api/agents/factor-lab/agent-tasks", methods=["POST"])
def factor_lab_create_agent_task():
    payload = request.get_json(silent=True) or {}
    instruction = str(payload.get("instruction") or "").strip()
    files = payload.get("files") if isinstance(payload.get("files"), list) else []
    file_items = [
        {
            "name": str(item.get("name") or ""),
            "size": item.get("size"),
            "type": str(item.get("type") or ""),
        }
        for item in files
        if isinstance(item, dict) and item.get("name")
    ]

    if not instruction and not file_items:
        return jsonify({"error": "instruction or files required"}), 400

    now = _utc_now_iso()
    task_id = f"task-agent-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}"
    task_dir = _agent_task_dir(task_id, create_root=True)
    artifacts_dir = task_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    request_payload = {
        "schema_version": "agent_task_request_v1",
        "task_id": task_id,
        "instruction": instruction,
        "files": file_items,
        "namespace": payload.get("namespace") or "quarantine",
        "data_source": payload.get("data_source") or "quant_api",
        "requires_quant_api": bool(payload.get("requires_quant_api", True)),
        "requested_at": payload.get("requested_at") or now,
        "received_at": now,
        "execution_mode": "trae_manual_handoff",
        "agent_policy": {
            "skill_selection": "backend_agent_decides",
            "target_namespace": "quarantine",
            "default_data_source": payload.get("data_source") or "quant_api",
            "frontend_runs_agent": False,
        },
        "trae_instruction": (
            "Read this request.json, decide whether the task is factor reproduction, mining, "
            "or evaluation. Use the official Quant API through the backend as the default data "
            "source, then write progress to status.json and outputs to artifacts/."
        ),
    }
    status_payload = {
        "schema_version": "agent_task_status_v1",
        "task_id": task_id,
        "status": "queued_for_trae",
        "current_gate": "G0",
        "message": "Request captured. Open this task directory from Trae to continue.",
        "updated_at": now,
    }

    _write_json(task_dir / "request.json", request_payload)
    _write_json(task_dir / "status.json", status_payload)

    return (
        jsonify(
            {
                **request_payload,
                **status_payload,
                "is_placeholder": False,
                "request_path": str(task_dir / "request.json"),
                "status_path": str(task_dir / "status.json"),
                "artifacts_dir": str(artifacts_dir),
            }
        ),
        201,
    )


@app.route("/api/agents/factor-lab/agent-tasks/<task_id>", methods=["GET"])
def factor_lab_agent_task(task_id: str):
    try:
        task_dir = _agent_task_dir(task_id)
    except ValueError:
        return jsonify({"error": "Invalid task_id"}), 400

    request_path = task_dir / "request.json"
    status_path = task_dir / "status.json"
    if not request_path.exists():
        return jsonify({"error": "Task not found"}), 404

    try:
        request_payload = json.loads(request_path.read_text(encoding="utf-8"))
        status_payload = json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() else {}
    except json.JSONDecodeError as exc:
        return jsonify({"error": "Task JSON is invalid", "detail": str(exc)}), 500

    return jsonify(
        {
            **request_payload,
            **status_payload,
            "request_path": str(request_path),
            "status_path": str(status_path),
            "artifacts_dir": str(task_dir / "artifacts"),
        }
    )


@app.route("/api/agents/factor-lab/agent-tasks/<task_id>/open-folder", methods=["POST"])
def factor_lab_open_agent_task_folder(task_id: str):
    try:
        task_dir = _agent_task_dir(task_id)
    except ValueError:
        return jsonify({"error": "Invalid task_id"}), 400

    if not task_dir.exists():
        return jsonify({"error": "Task not found"}), 404

    os.startfile(str(task_dir))
    return jsonify({"task_id": task_id, "opened": True, "folder_path": str(task_dir)})


@app.route("/api/agents/factor-lab/agent-tasks/<task_id>", methods=["DELETE"])
def factor_lab_delete_agent_task(task_id: str):
    try:
        task_dir = _agent_task_dir(task_id)
    except ValueError:
        return jsonify({"error": "Invalid task_id"}), 400

    if not task_dir.exists():
        return jsonify({"error": "Task not found"}), 404

    shutil.rmtree(task_dir)
    return jsonify({"task_id": task_id, "deleted": True})


@app.route("/api/agents/factor-lab/jobs", methods=["GET"])
def factor_lab_jobs():
    return jsonify({"items": list_factor_lab_jobs(_workspace())})


@app.route("/api/agents/factor-lab/jobs", methods=["POST"])
def factor_lab_create_job():
    payload = request.get_json(silent=True) or {}
    try:
        if payload.get("data_source") in {"quant_api", "real"}:
            job = run_factor_set_real_data_job(payload, _workspace())
        else:
            job = run_alpha101_research_job(payload, _workspace())
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(job), 201


@app.route("/api/agents/factor-lab/jobs/<job_id>", methods=["GET"])
def factor_lab_job_detail(job_id: str):
    payload = get_factor_lab_job(job_id, _workspace())
    if payload is None:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(payload)


@app.route("/api/agents/factor-lab/jobs/<job_id>/artifacts", methods=["GET"])
def factor_lab_job_artifacts(job_id: str):
    workspace = _workspace()
    if get_factor_lab_job(job_id, workspace) is None:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(
        {
            "job_id": job_id,
            "factor": request.args.get("factor"),
            "artifacts": list_job_artifacts(job_id, factor_name=request.args.get("factor"), workspace=workspace),
        }
    )


@app.route("/api/agents/factor-lab/artifacts/<job_id>/<artifact_kind>", methods=["GET"])
def factor_lab_job_artifact(job_id: str, artifact_kind: str):
    workspace = _workspace()
    if get_factor_lab_job(job_id, workspace) is None:
        return jsonify({"error": "Job not found"}), 404

    path = resolve_artifact_path(job_id, artifact_kind, factor_name=request.args.get("factor"), workspace=workspace)
    if path is None:
        return jsonify({"error": "Artifact not found"}), 404

    if not path.exists():
        return jsonify({"error": "Artifact file missing"}), 404
    return send_file(path, as_attachment=False, download_name=path.name)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8012"))
    host = os.getenv("HOST", "127.0.0.1")
    app.run(host=host, port=port, debug=False)
