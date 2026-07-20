from __future__ import annotations

import os
import sys
from dataclasses import asdict
from pathlib import Path

from flask import Flask, jsonify, request, send_file
from flask_cors import CORS


project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from research_core.factor_lab import (  # noqa: E402
    FactorLabWorkspaceConfig,
    check_amazingdata,
    get_alpha101_factor_detail,
    get_factor_lab_job,
    get_factor_lab_overview,
    list_alpha101_factors,
    list_factor_lab_jobs,
    run_alpha101_research_job,
    run_factor_set_research_job,
)
from contracts.backtest import ExternalSimulationRequest  # noqa: E402
from research_core.backtest_adapter.external_simulation import package_external_simulation  # noqa: E402


app = Flask(__name__)
CORS(app)


def _workspace() -> FactorLabWorkspaceConfig:
    return FactorLabWorkspaceConfig()


@app.route("/api/agents/factor-lab/overview", methods=["GET"])
def factor_lab_overview():
    return jsonify(get_factor_lab_overview(_workspace()))


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


@app.route("/api/agents/factor-lab/data-sources/amazingdata/check", methods=["POST"])
def factor_lab_check_amazingdata():
    payload = request.get_json(silent=True) or {}
    return jsonify(check_amazingdata(payload))


@app.route("/api/agents/factor-lab/jobs", methods=["POST"])
def factor_lab_create_job():
    payload = request.get_json(silent=True) or {}
    try:
        job = run_alpha101_research_job(payload, _workspace())
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(job), 201


@app.route("/api/agents/factor-lab/factor-set/jobs", methods=["POST"])
def factor_lab_create_factor_set_job():
    payload = request.get_json(silent=True) or {}
    try:
        job = run_factor_set_research_job(payload, _workspace())
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(job), 201


@app.route("/api/agents/factor-lab/external-sim/packages", methods=["POST"])
def factor_lab_create_external_sim_package():
    payload = request.get_json(silent=True) or {}
    try:
        sim_request = ExternalSimulationRequest(
            run_id=payload["run_id"],
            engine=payload["engine"],
            strategy_id=payload.get("strategy_id", payload["run_id"]),
            strategy_version=payload.get("strategy_version", "v1"),
            signal_path=payload["signal_path"],
            start_time=payload["start_time"],
            end_time=payload["end_time"],
            benchmark=payload.get("benchmark", ""),
            initial_cash=float(payload.get("initial_cash", 1_000_000.0)),
            slippage_bps=float(payload.get("slippage_bps", 0.0)),
            commission_bps=float(payload.get("commission_bps", 0.0)),
            metadata=payload.get("metadata", {}),
        )
        package = package_external_simulation(sim_request, output_dir=payload.get("output_dir") or None)
    except (KeyError, ValueError, FileNotFoundError) as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(asdict(package)), 201


@app.route("/api/agents/factor-lab/jobs/<job_id>", methods=["GET"])
def factor_lab_job_detail(job_id: str):
    payload = get_factor_lab_job(job_id, _workspace())
    if payload is None:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(payload)


@app.route("/api/agents/factor-lab/artifacts/<job_id>/<artifact_kind>", methods=["GET"])
def factor_lab_job_artifact(job_id: str, artifact_kind: str):
    payload = get_factor_lab_job(job_id, _workspace())
    if payload is None:
        return jsonify({"error": "Job not found"}), 404

    artifacts = payload.get("artifacts", {})
    path_str = artifacts.get(artifact_kind)
    if artifact_kind == "proof" and request.args.get("factor"):
        path_str = artifacts.get("proofs", {}).get(request.args["factor"])
    if not path_str:
        return jsonify({"error": "Artifact not found"}), 404

    path = Path(path_str)
    if not path.exists():
        return jsonify({"error": "Artifact file missing"}), 404
    return send_file(path, as_attachment=False, download_name=path.name)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8012"))
    app.run(host="0.0.0.0", port=port, debug=False)
