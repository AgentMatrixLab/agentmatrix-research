from __future__ import annotations

import os
import sys
from pathlib import Path

from flask import Flask, jsonify, request, send_file
from flask_cors import CORS


project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from research_core.factor_lab import (  # noqa: E402
    FactorLabWorkspaceConfig,
    get_alpha101_factor_detail,
    get_factor_lab_job,
    get_factor_lab_overview,
    list_alpha101_factors,
    list_factor_lab_jobs,
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


app = Flask(__name__)


def _cors_origins() -> list[str]:
    raw = os.getenv(
        "FACTOR_LAB_CORS_ORIGINS",
        "http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:8012,http://localhost:8012,null",
    )
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


CORS(app, resources={r"/api/*": {"origins": _cors_origins()}})


def _workspace() -> FactorLabWorkspaceConfig:
    return FactorLabWorkspaceConfig()


@app.route("/api/agents/factor-lab/overview", methods=["GET"])
def factor_lab_overview():
    return jsonify(get_factor_lab_overview(_workspace()))


@app.route("/api/agents/factor-lab/factor-library", methods=["GET"])
def factor_lab_factor_library():
    return jsonify(build_factor_library_view(_workspace()))


@app.route("/api/agents/factor-lab/health", methods=["GET"])
def factor_lab_health():
    return jsonify({"status": "ok", "service": "factor_lab", "local_flask": True})


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


@app.route("/api/agents/factor-lab/jobs", methods=["GET"])
def factor_lab_jobs():
    return jsonify({"items": list_factor_lab_jobs(_workspace())})


@app.route("/api/agents/factor-lab/jobs", methods=["POST"])
def factor_lab_create_job():
    payload = request.get_json(silent=True) or {}
    try:
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
