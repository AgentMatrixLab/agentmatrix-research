import unittest

import pandas as pd

from research_core.factor_library.validation import compute_forward_returns, compute_monthly_ic
from research_core.factor_library.batch_compute import batch_compute_factors


class FactorLibraryValidationTest(unittest.TestCase):
    def test_monthly_ic_uses_forward_return_output(self) -> None:
        price_panel = pd.DataFrame(
            {
                "date": pd.to_datetime(
                    [
                        "2024-01-31",
                        "2024-02-29",
                        "2024-01-31",
                        "2024-02-29",
                        "2024-01-31",
                        "2024-02-29",
                    ]
                ),
                "code": ["000001.SZ", "000001.SZ", "000002.SZ", "000002.SZ", "000003.SZ", "000003.SZ"],
                "close": [10.0, 11.0, 20.0, 18.0, 30.0, 33.0],
            }
        )
        factor_panel = pd.DataFrame(
            {
                "date": pd.to_datetime(["2024-01-31", "2024-01-31", "2024-01-31"]),
                "code": ["000001.SZ", "000002.SZ", "000003.SZ"],
                "alpha1": [0.5, -0.2, 0.7],
            }
        )

        returns = compute_forward_returns(price_panel, periods=1)
        ic = compute_monthly_ic(factor_panel, returns)

        self.assertEqual(list(ic.columns), ["date", "alpha1"])
        self.assertEqual(len(ic), 1)
        self.assertFalse(pd.isna(ic.loc[0, "alpha1"]))

    def test_monthly_ic_can_read_legacy_return_column_when_explicit(self) -> None:
        factor_panel = pd.DataFrame(
            {
                "date": pd.to_datetime(["2024-01-31", "2024-01-31", "2024-01-31"]),
                "code": ["000001.SZ", "000002.SZ", "000003.SZ"],
                "alpha1": [1.0, 2.0, 3.0],
            }
        )
        returns = pd.DataFrame(
            {
                "date": pd.to_datetime(["2024-01-31", "2024-01-31", "2024-01-31"]),
                "code": ["000001.SZ", "000002.SZ", "000003.SZ"],
                "return": [0.1, 0.2, 0.3],
            }
        )

        ic = compute_monthly_ic(factor_panel, returns, return_col="return")

        self.assertEqual(ic.loc[0, "alpha1"], 1.0)

    def test_batch_compute_factors_renames_actual_factor_columns_dynamically(self) -> None:
        panel = pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=25, freq="B").repeat(3),
                "code": ["000001.SZ", "000002.SZ", "000003.SZ"] * 25,
                "open": [10.0, 20.0, 30.0] * 25,
                "high": [11.0, 21.0, 31.0] * 25,
                "low": [9.0, 19.0, 29.0] * 25,
                "close": [10.5, 20.5, 30.5] * 25,
                "volume": [1000.0, 2000.0, 3000.0] * 25,
                "amount": [10500.0, 41000.0, 91500.0] * 25,
            }
        )

        result = batch_compute_factors(panel, factor_sets=["wq101"])

        self.assertIn("wq101_alpha1", result.columns)
        self.assertIn("wq101_alpha10", result.columns)
        self.assertNotIn("wq101_alpha11", result.columns)
        self.assertEqual(result.columns.tolist(), ["date", "code", *[f"wq101_alpha{i}" for i in range(1, 11)]])


if __name__ == "__main__":
    unittest.main()
