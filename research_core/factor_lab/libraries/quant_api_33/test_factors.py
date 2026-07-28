from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from research_core.factor_lab.libraries.quant_api_33 import (
    IMPLEMENTED_QUANT_API_33_FACTORS,
    compute_quant_api_33_factors,
    quant_api_33_specs,
)


class QuantApi33FactorTest(unittest.TestCase):
    def setUp(self) -> None:
        dates = pd.bdate_range("2024-01-01", periods=280)
        rows = []
        for code_index, code in enumerate(["000001.SZ", "000002.SZ", "600000.SH"]):
            base = 10.0 + code_index
            for idx, date in enumerate(dates):
                close = base + idx * 0.03 + np.sin(idx / 9.0) * 0.2
                open_ = close * 0.995
                high = close * 1.02
                low = close * 0.98
                volume = 1000000 + code_index * 10000 + idx * 1000
                rows.append(
                    {
                        "date": date,
                        "code": code,
                        "open": open_,
                        "high": high,
                        "low": low,
                        "close": close,
                        "volume": volume,
                        "amount": volume * close,
                    }
                )
        self.panel = pd.DataFrame(rows)

    def test_compute_all_quant_api_33_columns(self) -> None:
        result = compute_quant_api_33_factors(self.panel)

        self.assertEqual(result.columns.tolist(), ["date", "code", *IMPLEMENTED_QUANT_API_33_FACTORS])
        self.assertEqual(len(result), len(self.panel))
        self.assertGreater(result["ret_1m"].notna().sum(), 0)
        self.assertGreater(result["rsi_14"].notna().sum(), 0)
        self.assertTrue(result["roe_ttm"].isna().all())

    def test_financial_factors_use_supplied_raw_fields(self) -> None:
        panel = self.panel.copy()
        panel["net_profit_ttm"] = 10.0
        panel["equity"] = 100.0
        panel["assets"] = 200.0
        panel["revenue_ttm"] = 50.0
        panel["liabilities"] = 80.0
        panel["revenue_yoy"] = 0.2
        panel["profit_yoy"] = 0.3
        panel["eps_yoy"] = 0.4

        result = compute_quant_api_33_factors(panel, factor_names=["roe_ttm", "asset_turnover", "eps_yoy"])

        self.assertAlmostEqual(result["roe_ttm"].dropna().iloc[0], 0.1)
        self.assertAlmostEqual(result["asset_turnover"].dropna().iloc[0], 0.25)
        self.assertAlmostEqual(result["eps_yoy"].dropna().iloc[0], 0.4)

    def test_specs_expose_exact_33_names(self) -> None:
        specs = quant_api_33_specs()

        self.assertEqual([item["factor_name"] for item in specs], list(IMPLEMENTED_QUANT_API_33_FACTORS))
        self.assertEqual(len(specs), 33)


if __name__ == "__main__":
    unittest.main()
