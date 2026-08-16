from __future__ import annotations
import unittest
from research_core.strategy_analytics import analyze_window, combine_portfolio, evaluate_risk_rules, attribute_sub_strategies
from research_core.backtest_adapter.custom_engine.ledger import rebuild_position_ledger

CURVE=[{"date":"2024-01-01","nav":1.0,"benchmark":1.0,"drawdown":0},{"date":"2024-01-02","nav":1.1,"benchmark":1.02,"drawdown":0},{"date":"2024-01-03","nav":1.05,"benchmark":1.01,"drawdown":-0.04545}]

class StrategyAnalyticsTest(unittest.TestCase):
    def test_window_metrics_are_derived(self):
        m=analyze_window(CURVE)
        self.assertAlmostEqual(m["total_return"],.05)
        self.assertIsNotNone(m["beta"])
        self.assertGreater(m["max_drawdown"],0)

    def test_ledger_rebuilds_cost_cash_and_pnl(self):
        ledger=rebuild_position_ledger([{"time":"1","code":"600519.SH","side":"BUY","qty":100,"price":10,"fee":5},{"time":"2","code":"600519.SH","side":"SELL","qty":40,"price":12,"fee":5}],10000,{"600519.SH":11})
        self.assertEqual(ledger["positions"][0]["quantity"],60)
        self.assertGreater(ledger["realized_pnl"],0)
        self.assertAlmostEqual(ledger["total_equity"],10130)

    def test_portfolio_and_risk_and_attribution(self):
        p=combine_portfolio([(.5,CURVE),(.5,CURVE)])
        self.assertEqual(len(p["curve"]),3)
        self.assertEqual(p["methodology"], "shared_cash_sleeve_ledger_v1")
        self.assertGreater(p["execution_cost"], 0)
        self.assertGreaterEqual(p["ending_cash"], -1e-8)
        alerts=evaluate_risk_rules({"max_drawdown":.3,"volatility":.1,"turnover":.2},[{"weight":.7},{"weight":.3}])
        self.assertTrue(any(a["triggered"] for a in alerts))
        self.assertFalse(attribute_sub_strategies([])["available"])
        self.assertTrue(attribute_sub_strategies([{"sub_strategy":"a","realized_pnl":10,"commission":1}])["available"])

if __name__ == "__main__": unittest.main()
