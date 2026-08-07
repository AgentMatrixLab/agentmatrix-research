from __future__ import annotations

import os
import json
import sys
from pathlib import Path

from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from research_core.strategy_dashboard import StrategyDashboardStore, StrategyResultNotFound  # noqa: E402


def create_app(*, result_dir: str | Path | None = None, publication_status: str | None = None) -> Flask:
    app = Flask(__name__)
    CORS(app)
    dashboard_root = PROJECT_ROOT / "frontend" / "quant-desk-dashboard"
    configured_result_dir = result_dir or os.getenv("STRATEGY_BACKTEST_RESULT_DIR")
    configured_publication_status = publication_status or os.getenv("STRATEGY_RESULT_PUBLICATION_STATUS", "published")

    def read_status(path_value: str | None) -> dict | None:
        if not path_value:
            return None
        try:
            return json.loads(Path(path_value).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def store() -> StrategyDashboardStore:
        return StrategyDashboardStore(configured_result_dir or None, configured_publication_status)

    @app.get("/healthz")
    def health():
        strategies = store().list_strategies()
        return jsonify({"status": "ok", "service": "strategy-dashboard", "strategies": len(strategies)})

    @app.get("/quant-desk/")
    def dashboard():
        return send_from_directory(dashboard_root, "index.html")

    @app.get("/quant-desk/<path:filename>")
    def dashboard_asset(filename: str):
        target = dashboard_root / filename
        if target.is_file():
            return send_from_directory(dashboard_root, filename)
        return send_from_directory(dashboard_root, "index.html")

    @app.get("/api/strategy-dashboard/strategies")
    def strategies():
        return jsonify(store().list_strategies())

    @app.get("/api/strategy-dashboard/status")
    def operating_status():
        readiness = read_status(os.getenv("STRATEGY_DATA_READINESS_FILE"))
        batch = read_status(os.getenv("STRATEGY_BATCH_STATUS_FILE"))
        return jsonify({
            "data": {
                "status": readiness.get("status") if readiness else "unknown",
                "data_version": readiness.get("data_version") if readiness else None,
                "required_failures": readiness.get("required_failures", []) if readiness else [],
            },
            "batch": {
                "batch_id": batch.get("batch_id") if batch else None,
                "finished_at": batch.get("finished_at") if batch else None,
                "strategies": batch.get("strategies", []) if batch else [],
            },
        })

    @app.get("/api/strategy-dashboard/strategies/<strategy_id>")
    def strategy(strategy_id: str):
        try:
            return jsonify(store().get_strategy(strategy_id))
        except StrategyResultNotFound:
            return jsonify({"error": "Strategy result not found"}), 404

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "8013")), debug=False)
