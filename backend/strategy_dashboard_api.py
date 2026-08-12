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
from research_core.strategy_analytics import analyze_window, combine_portfolio, evaluate_risk_rules, attribute_sub_strategies  # noqa: E402


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

    @app.get("/api/strategy-dashboard/data-capabilities")
    def data_capabilities():
        """Declare real analytical inputs; absent datasets remain unavailable."""
        dataset_dir = Path(os.getenv("STRATEGY_DATASET_DIR", ""))
        benchmark_files = {
            "csi300": "csi300_index.parquet", "csi500": "csi500_index.parquet", "csi1000": "csi1000_index.parquet"
        }
        benchmarks = [{"key": key, "available": bool(dataset_dir and (dataset_dir / filename).is_file()), "source": filename}
                      for key, filename in benchmark_files.items()]
        stock_info = dataset_dir / "stock_info.parquet" if dataset_dir else None
        return jsonify({"benchmarks": benchmarks,
                        "exposures": {"industry": False, "market_cap": False, "security_name": bool(stock_info and stock_info.is_file())},
                        "notes": ["行业和市值源未接入时接口不构造估算值"]})

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

    @app.get("/api/strategy-dashboard/strategies/<strategy_id>/analytics")
    def strategy_analytics(strategy_id: str):
        detail, error = detail_or_404(strategy_id)
        if error:
            return error
        metrics = analyze_window(detail["equity_curve"], request.args.get("start"), request.args.get("end"))
        return jsonify({"strategy_id": strategy_id, "window": {"start": request.args.get("start"), "end": request.args.get("end")}, "metrics": metrics})

    @app.get("/api/strategy-dashboard/strategies/<strategy_id>/risk-alerts")
    def strategy_risk_alerts(strategy_id: str):
        detail, error = detail_or_404(strategy_id)
        if error:
            return error
        return jsonify(evaluate_risk_rules(detail["metrics"], detail["positions"], {"gross": detail["gross_exposure"]}))

    @app.get("/api/strategy-dashboard/strategies/<strategy_id>/attribution")
    def strategy_attribution(strategy_id: str):
        detail, error = detail_or_404(strategy_id)
        if error:
            return error
        return jsonify(attribute_sub_strategies(detail["trades"]))

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
        rows = [{"code": p["symbol"], "name": p.get("name") or p["symbol"], "industry": p.get("industry") or "未提供",
                 "qty": p.get("quantity") or 0, "cost": p.get("average_cost") or 0, "price": p.get("last_price") or 0,
                 "value": p.get("market_value") or 0, "pnl": p.get("unrealized_pnl") or 0,
                 "pnlPct": p.get("unrealized_pnl_pct") or 0, "weight": p["weight"]} for p in detail["positions"]]
        total = sum(abs(p["weight"]) for p in detail["positions"])
        top5 = sum(abs(p["weight"]) for p in detail["positions"][:5])
        hhi = sum(p["weight"] ** 2 for p in detail["positions"])
        industries = {}
        caps = {"大盘": 0.0, "中盘": 0.0, "小盘": 0.0}
        for p in detail["positions"]:
            if p.get("industry"):
                industries[p["industry"]] = industries.get(p["industry"], 0.0) + float(p.get("weight") or 0)
            cap = p.get("market_cap")
            if cap is not None:
                bucket = "大盘" if float(cap) >= 50_000_000_000 else ("中盘" if float(cap) >= 10_000_000_000 else "小盘")
                caps[bucket] += float(p.get("weight") or 0)
        return jsonify({"count": len(rows), "totalWeight": total, "top5Weight": top5, "hhi": hhi,
                        "industries": [{"name": k, "weight": v} for k, v in sorted(industries.items(), key=lambda x: -x[1])],
                        "marketCap": [{"name": k, "weight": v} for k, v in caps.items() if v],
                        "exposureAvailable": {"industry": bool(industries), "marketCap": any(caps.values())}, "rows": rows})

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
                        "volatility": metrics.get("volatility"), "beta": metrics.get("beta"), "leverage": detail.get("gross_exposure"),
                        "alerts": evaluate_risk_rules(metrics, detail["positions"], {"gross": detail["gross_exposure"]}), "drawdownEvents": events, "monthlyReturns": monthly_returns})

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
        start, end = body.get("start"), body.get("end")
        sliced = [(weight, [p for p in detail["equity_curve"] if (not start or p["date"] >= start) and (not end or p["date"] <= end)])
                  for weight, detail in details]
        result = combine_portfolio(
            sliced,
            body.get("rebalance", "monthly"),
            initial_cash=float(body.get("initialCash") or 1_000_000),
            commission_bps=float(body.get("commissionBps") or 3),
            slippage_bps=float(body.get("slippageBps") or 5),
        )
        maps = [dict((p["date"], p) for p in detail["equity_curve"]) for _, detail in details]
        dates = [p["date"] for p in result["curve"]]
        dates = [d for d in dates if (not start or d >= start) and (not end or d <= end)]
        if len(dates) < 2:
            return jsonify({"error": "No common NAV window"}), 400
        nav = [p for p in result["curve"] if (not start or p["date"] >= start) and (not end or p["date"] <= end)]
        daily = [nav[i]["nav"] / nav[i-1]["nav"] - 1 for i in range(1, len(nav))]
        mean = sum(daily) / len(daily)
        variance = sum((r - mean) ** 2 for r in daily) / len(daily)
        vol = math.sqrt(variance) * math.sqrt(252)
        annual = nav[-1]["nav"] ** (252 / len(daily)) - 1
        return jsonify({"methodology": result["methodology"], "nav": nav, "weights": items,
                        "ledger": {"initialCash": result["initial_cash"], "endingCash": result["ending_cash"],
                                   "executionCost": result["execution_cost"], "rebalanceTrades": len(result["trades"])},
                        "kpis": {"totalReturn": nav[-1]["nav"] - 1,
                        "annualReturn": annual, "sharpe": mean * 252 / vol if vol else 0,
                        "maxDrawdown": min(p["drawdown"] for p in nav), "winRate": sum(r > 0 for r in daily) / len(daily),
                        "volatility": vol}})

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "8013")), debug=False)
