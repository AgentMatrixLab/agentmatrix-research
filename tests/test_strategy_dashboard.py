from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from research_core.strategy_dashboard import StrategyDashboardStore, StrategyResultNotFound
from backend.strategy_dashboard_api import create_app


class StrategyDashboardStoreTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        payload = {
            "run_id": "run-1",
            "status": "completed",
            "engine": "custom_legacy_bridge",
            "strategy_id": "dividend-v6",
            "strategy_version": "v6",
            "benchmark": "000300.SH",
            "metrics": {"total_return": 0.1, "annualized_return": 0.2, "benchmark_return": 0.03, "excess_return": 0.07, "max_drawdown": 0.08, "sharpe": 1.2, "volatility": 0.15, "turnover": 0.4, "win_rate": 0.52},
            "equity_curve": [{"timestamp": "2024-01-02", "strategy_nav": 1.0, "benchmark_nav": 1.0, "drawdown": 0.0}, {"timestamp": "2024-01-03", "strategy_nav": 1.1, "benchmark_nav": 1.03, "drawdown": -0.01}],
            "trades": [{"traded_at": "2024-01-03", "symbol": "600519.SH", "side": "BUY", "quantity": 100, "price": 10, "commission": 5, "slippage": 0}],
            "holdings": [{"as_of": "2024-01-03", "weights": {"600519.SH": 0.6, "000001.SZ": 0.4}, "exposures": {"gross": 1.0}}],
            "diagnostics": {"strategy_name": "红利策略v6", "data_version": "2024-01-03", "quality": {"passed": True}},
        }
        (self.root / "run-1.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        older = {**payload, "run_id": "run-0", "metrics": {**payload["metrics"], "sharpe": 9.0}}
        (self.root / "run-0.json").write_text(json.dumps(older, ensure_ascii=False), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_lists_and_builds_read_only_detail(self):
        store = StrategyDashboardStore(self.root)
        self.assertEqual(store.list_strategies()[0]["name"], "红利策略v6")
        self.assertEqual(store.list_strategies()[0]["run_count"], 2)
        self.assertEqual(store.list_strategies()[0]["rank"], 1)
        self.assertEqual(store.list_strategies()[0]["publication_status"], "published")
        self.assertEqual(store.list_strategies()[0]["data_version"], "2024-01-03")
        detail = store.get_strategy("dividend-v6")
        self.assertEqual(detail["equity_curve"][-1]["nav"], 1.1)
        self.assertEqual(detail["positions"][0]["symbol"], "600519.SH")
        self.assertEqual(detail["trades"][0]["amount"], 1000.0)

    def test_review_directory_is_explicitly_unpublished(self):
        item = StrategyDashboardStore(self.root, "review").list_strategies()[0]
        self.assertEqual(item["publication_status"], "review")

    def test_missing_strategy_raises(self):
        with self.assertRaises(StrategyResultNotFound):
            StrategyDashboardStore(self.root).get_strategy("missing")

    def test_flask_serves_dashboard_and_real_contract(self):
        app = create_app(result_dir=self.root, publication_status="review")
        with app.test_client() as client:
            page = client.get("/quant-desk/")
            self.assertEqual(page.status_code, 200)
            self.assertIn(b"QUANT", page.data)
            self.assertIn("晨曦引擎".encode(), page.data)
            self.assertIn("策略组合".encode(), page.data)
            self.assertIn("风险中心".encode(), page.data)
            self.assertIn("回测工作台".encode(), page.data)
            self.assertIn("策略对比".encode(), page.data)
            self.assertIn("组合构建".encode(), page.data)
            self.assertIn(b'id="strategySearch"', page.data)
            page.close()

            script = client.get("/quant-desk/app.js")
            self.assertEqual(script.status_code, 200)
            self.assertIn(b"buildPortfolio", script.data)
            self.assertIn(b"buildRisk", script.data)
            script.close()

            workbench = client.get("/quant-desk/workbench.js")
            self.assertEqual(workbench.status_code, 200)
            self.assertIn(b"backtest-jobs", workbench.data)
            workbench.close()

            analytics = client.get("/quant-desk/analytics.js")
            self.assertEqual(analytics.status_code, 200)
            self.assertIn(b"correlationMatrix", analytics.data)
            self.assertIn(b"quantDeskPortfolios", analytics.data)
            analytics.close()

            strategies = client.get("/api/strategy-dashboard/strategies")
            self.assertEqual(strategies.status_code, 200)
            self.assertEqual(strategies.get_json()[0]["id"], "dividend-v6")
            self.assertEqual(strategies.get_json()[0]["publication_status"], "review")
            strategies.close()

            detail = client.get("/api/strategy-dashboard/strategies/dividend-v6")
            self.assertEqual(detail.status_code, 200)
            self.assertEqual(len(detail.get_json()["positions"]), 2)
            detail.close()

            missing = client.get("/api/strategy-dashboard/strategies/missing")
            self.assertEqual(missing.status_code, 404)
            missing.close()

if __name__ == "__main__":
    unittest.main()
