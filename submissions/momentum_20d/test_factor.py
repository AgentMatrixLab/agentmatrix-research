"""
20日动量因子单元测试。

验证：
1. 合成数据上的公式正确性
2. 边界情况不崩溃
"""
import unittest
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from factor import compute


class TestMomentum20d(unittest.TestCase):
    def test_basic_momentum(self):
        """用合成数据验证 20 日动量公式"""
        # 构造一只股票 25 天的数据: 价格线性增长 10 → 12.4
        dates = pd.date_range("2024-01-01", periods=25, freq="B")
        records = []
        base = 10.0
        for i, date in enumerate(dates):
            records.append({
                "date": date,
                "code": "000001",
                "close": base * (1 + i * 0.01),  # 每天涨 1%
                "open": base * (1 + i * 0.01),
                "high": base * (1 + i * 0.01) * 1.005,
                "low": base * (1 + i * 0.01) * 0.995,
                "volume": 1000000,
                "amount": 10000000,
            })

        panel = pd.DataFrame(records)
        result = compute(panel)

        # 前20天应为 NaN（window=20 需要21天才有一个有效值）
        self.assertTrue(result.iloc[:20].isna().all(),
                        f"前20天应为NaN，实际: {result.iloc[:20].tolist()}")

        # 第21天（index=20）: close=10*(1+20*0.01)=12.0, close_t-20=10*(1+0*0.01)=10.0
        # momentum = (12.0 - 10.0) / 10.0 = 0.20
        expected = ((base * (1 + 20 * 0.01)) - (base * (1 + 0 * 0.01))) / (base * (1 + 0 * 0.01))
        actual = result.iloc[20]
        self.assertAlmostEqual(actual, expected, places=6,
                               msg=f"第21天动量应为 {expected:.6f}，实际 {actual:.6f}")

    def test_multiple_stocks(self):
        """多只股票独立计算"""
        dates = pd.date_range("2024-01-01", periods=25, freq="B")
        records = []
        for code, base in [("000001", 10.0), ("000002", 20.0)]:
            for i, date in enumerate(dates):
                records.append({
                    "date": date, "code": code,
                    "close": base * (1 + i * 0.01),
                    "open": base, "high": base * 1.01,
                    "low": base * 0.99, "volume": 1000000,
                    "amount": 10000000,
                })

        panel = pd.DataFrame(records)
        result = compute(panel)

        # 两只股票的结果应相同（增长率相同）
        stock1 = result[panel["code"] == "000001"].reset_index(drop=True)
        stock2 = result[panel["code"] == "000002"].reset_index(drop=True)
        pd.testing.assert_series_equal(stock1, stock2, check_names=False,
                                       obj="两只股票的因子值应完全一致")

    def test_short_panel_no_crash(self):
        """数据不足一个窗口时不崩溃"""
        panel = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=5, freq="B"),
            "code": ["000001"] * 5,
            "close": [10.0, 10.1, 10.2, 10.3, 10.4],
            "open": [10.0] * 5,
            "high": [10.5] * 5,
            "low": [9.5] * 5,
            "volume": [1000000] * 5,
            "amount": [10000000] * 5,
        })

        result = compute(panel)
        self.assertEqual(len(result), 5)
        # 窗口=20 但只有 5 天数据，应全为 NaN
        self.assertTrue(result.isna().all())


if __name__ == "__main__":
    unittest.main()
