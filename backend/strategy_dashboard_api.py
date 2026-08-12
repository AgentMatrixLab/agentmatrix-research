from __future__ import annotations

import os
import json
import sys
from pathlib import Path
from datetime import datetime
import math

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from research_core.strategy_dashboard import StrategyDashboardStore, StrategyResultNotFound  # noqa: E402
from research_core.backtest_jobs import BacktestJobService, BacktestJobStore, JobRequestError  # noqa: E402


def create_app(*, result_dir: str | Path | None = None, publication_status: str | None = None) -> Flask:
    app = Flask(__name__)
    CORS(app)
    react_root = PROJECT_ROOT / "frontend" / "quant-desk-react"
    dashboard_root = react_root if (react_root / "index.html").is_file() else PROJECT_ROOT / "frontend" / "quant-desk-dashboard"
    configured_result_dir = result_dir or os.getenv("STRATEGY_BACKTEST_RESULT_DIR")
    configured_publication_status = publication_status or os.getenv("STRATEGY_RESULT_PUBLICATION_STATUS", "published")
    job_store = BacktestJobStore(os.getenv("BACKTEST_JOB_DB", str(PROJECT_ROOT / "runtime" / "backtest_jobs" / "jobs.sqlite3")))
    job_service = BacktestJobService(job_store, os.getenv("STRATEGY_REGISTRY_FILE", str(PROJECT_ROOT / "config" / "strategy_registry.json")))

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

    @app.get("/api/strategy-dashboard/backtest-capabilities")
    def backtest_capabilities():
        return jsonify(job_service.capabilities())

    @app.get("/api/strategy-dashboard/backtest-jobs")
    def backtest_jobs():
        return jsonify(job_store.list(min(max(int(request.args.get("limit", 25)), 1), 100)))

    @app.get("/api/strategy-dashboard/backtest-jobs/<job_id>")
    def backtest_job(job_id: str):
        try:
            return jsonify(job_store.get(job_id))
        except KeyError:
            return jsonify({"error": "Backtest job not found"}), 404

    @app.post("/api/strategy-dashboard/backtest-jobs")
    def submit_backtest_job():
        try:
            job_service.authorize(request.headers.get("X-Backtest-Token", ""))
            return jsonify(job_service.submit(request.get_json(silent=True) or {})), 202
        except PermissionError as exc:
            return jsonify({"error": str(exc)}), 403
        except JobRequestError as exc:
            return jsonify({"error": str(exc)}), 400

    @app.get("/api/strategy-dashboard/strategies/<strategy_id>")
    def strategy(strategy_id: str):
        try:
            return jsonify(store().get_strategy(strategy_id))
        except StrategyResultNotFound:
            return jsonify({"error": "Strategy result not found"}), 404

    # Compatibility endpoints for the teammate React presentation. These are
    # read-only projections of canonical AgentMatrix results, not a second
    # database or engine.
    @app.get("/api/strategies")
    def react_strategies():
        return jsonify([{
            "id": s["id"], "name": s["name"], "tag": "已发布" if s["publication_status"] == "published" else "研究验证",
            "status": "running", "version": s["version"], "annualReturn": s["annualized_return"],
            "sharpe": s["sharpe"], "todayReturn": 0,
        } for s in store().list_strategies()])

    def detail_or_404(strategy_id: str):
        try:
            return store().get_strategy(strategy_id), None
        except StrategyResultNotFound:
            return None, (jsonify({"error": "Strategy result not found"}), 404)

    @app.get("/api/positions")
    def react_positions():
        detail, error = detail_or_404(request.args.get("strategyId", ""))
        if error:
            return error
        rows = [{"code": p["symbol"], "name": p["symbol"], "industry": "未提供", "qty": 0, "cost": 0,
                 "price": 0, "value": 0, "pnl": 0, "pnlPct": 0, "weight": p["weight"]} for p in detail["positions"]]
        total = sum(abs(p["weight"]) for p in detail["positions"])
        top5 = sum(abs(p["weight"]) for p in detail["positions"][:5])
        hhi = sum(p["weight"] ** 2 for p in detail["positions"])
        return jsonify({"count": len(rows), "totalWeight": total, "top5Weight": top5, "hhi": hhi,
                        "industries": [{"name": "行业数据未提供", "weight": total}] if rows else [],
                        "marketCap": [], "rows": rows})

    @app.get("/api/trades")
    def react_trades():
        detail, error = detail_or_404(request.args.get("strategyId", ""))
        if error:
            return error
        side, query = request.args.get("side", "").lower(), request.args.get("q", "").lower()
        rows = [{"time": t["time"], "code": t["symbol"], "name": t["symbol"], "side": t["side"].lower(),
                 "price": t["price"], "qty": t["quantity"], "amount": t["amount"], "fee": t["commission"]}
                for t in detail["trades"]]
        rows = [r for r in rows if (not side or r["side"] == side) and (not query or query in r["code"].lower())]
        page, size = max(int(request.args.get("page", 1)), 1), min(max(int(request.args.get("pageSize", 20)), 1), 1000)
        return jsonify({"total": len(rows), "page": page, "pageSize": size, "rows": rows[(page-1)*size:page*size]})

    @app.get("/api/risk/overview")
    def react_risk():
        detail, error = detail_or_404(request.args.get("strategyId", ""))
        if error:
            return error
        curve, metrics = detail["equity_curve"], detail["metrics"]
        monthly = {}
        for p in curve:
            monthly.setdefault(str(p["date"])[:7], []).append(float(p["nav"]))
        monthly_returns = [{"month": month, "ret": vals[-1] / vals[0] - 1 if vals and vals[0] else 0} for month, vals in sorted(monthly.items())]
        events, active = [], None
        for p in curve:
            dd = float(p.get("drawdown") or 0)
            if dd < -0.02 and active is None:
                active = {"start": p["date"], "trough": p["date"], "recovered": None, "depth": dd, "durationDays": 0}
            if active:
                if dd < active["depth"]:
                    active.update({"depth": dd, "trough": p["date"]})
                active["durationDays"] += 1
                if dd >= -0.000001:
                    active["recovered"] = p["date"]
                    events.append(active); active = None
        if active:
            events.append(active)
        return jsonify({"currentDrawdown": curve[-1]["drawdown"] if curve else 0, "var95": metrics.get("var_95", 0),
                        "volatility": metrics.get("volatility", 0), "beta": metrics.get("beta", 0), "leverage": 1,
                        "alerts": [], "drawdownEvents": events, "monthlyReturns": monthly_returns})

    @app.post("/api/portfolio/backtest")
    def react_portfolio_analysis():
        body = request.get_json(silent=True) or {}
        items = body.get("items") or []
        if len(items) < 2:
            return jsonify({"error": "At least two strategies are required"}), 400
        total_weight = sum(float(item.get("weight") or 0) for item in items)
        if not math.isclose(total_weight, 1.0, abs_tol=0.001):
            return jsonify({"error": "Weights must sum to one"}), 400
        details = []
        for item in items:
            detail, error = detail_or_404(str(item.get("strategyId") or ""))
            if error:
                return error
            details.append((float(item["weight"]), detail))
        maps = [dict((p["date"], p) for p in detail["equity_curve"]) for _, detail in details]
        dates = sorted(set.intersection(*(set(m) for m in maps))) if maps else []
        start, end = body.get("start"), body.get("end")
        dates = [d for d in dates if (not start or d >= start) and (not end or d <= end)]
        if len(dates) < 2:
            return jsonify({"error": "No common NAV window"}), 400
        bases = [m[dates[0]]["nav"] for m in maps]
        nav, peak = [], 1.0
        for day in dates:
            value = sum(details[i][0] * maps[i][day]["nav"] / bases[i] for i in range(len(details)))
            benchmark = sum(details[i][0] * maps[i][day]["benchmark"] / maps[i][dates[0]]["benchmark"] for i in range(len(details)))
            peak = max(peak, value)
            nav.append({"date": day, "nav": value, "benchmark": benchmark, "drawdown": value / peak - 1})
        daily = [nav[i]["nav"] / nav[i-1]["nav"] - 1 for i in range(1, len(nav))]
        mean = sum(daily) / len(daily)
        variance = sum((r - mean) ** 2 for r in daily) / len(daily)
        vol = math.sqrt(variance) * math.sqrt(252)
        annual = nav[-1]["nav"] ** (252 / len(daily)) - 1
        return jsonify({"nav": nav, "weights": items, "kpis": {"totalReturn": nav[-1]["nav"] - 1,
                        "annualReturn": annual, "sharpe": mean * 252 / vol if vol else 0,
                        "maxDrawdown": min(p["drawdown"] for p in nav), "winRate": sum(r > 0 for r in daily) / len(daily),
                        "volatility": vol}})

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "8013")), debug=False)
