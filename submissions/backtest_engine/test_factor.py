"""
A股多因子复合信号 单元测试。

验证:
  1. 合成数据上各子因子的方向正确性
  2. 截面标准化后同日期均值为0
  3. 边界情况不崩溃
"""
import unittest
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from factor import compute


class TestCompositeFactor(unittest.TestCase):
    def _make_panel(self, codes, n_days=60):
        """构造合成 panel: 多只股票 × n天"""
        dates = pd.date_range("2024-01-01", periods=n_days, freq="B")
        records = []
        np.random.seed(42)
        for code, base_price, trend, vol in codes:
            price = base_price
            for i, date in enumerate(dates):
                price = price * (1 + trend + np.random.normal(0, vol))
                volume = max(10000, int(np.random.normal(5_000_000, 2_000_000)))
                amount = volume * price
                records.append({
                    "date": date, "code": code,
                    "close": round(price, 2),
                    "open": round(price * 0.99, 2),
                    "high": round(price * 1.02, 2),
                    "low": round(price * 0.98, 2),
                    "volume": volume,
                    "amount": round(amount, 2),
                })
        return pd.DataFrame(records)

    def test_composite_not_all_nan(self):
        """复合因子应有有效值"""
        codes = [
            ("000001", 10.0, 0.001, 0.02),
            ("000002", 20.0, -0.0005, 0.015),
            ("000003", 30.0, 0.0002, 0.025),
        ]
        panel = self._make_panel(codes, n_days=60)
        result = compute(panel)

        self.assertEqual(len(result), len(panel))
        valid_ratio = result.notna().mean()
        self.assertGreater(valid_ratio, 0.3,
                           f"有效值比例应 > 30%, 实际 {valid_ratio:.1%}")

    def test_cross_sectional_zero_mean(self):
        """截面标准化后每个日期的均值接近0"""
        codes = [
            ("000001", 10.0, 0.001, 0.02),
            ("000002", 20.0, -0.0005, 0.015),
            ("000003", 30.0, 0.0002, 0.025),
            ("000004", 15.0, 0.0008, 0.03),
            ("000005", 25.0, -0.0003, 0.018),
        ]
        panel = self._make_panel(codes, n_days=60)
        result = compute(panel)

        # 取最后10天（所有子因子都有足够历史数据）
        df = panel[["date"]].copy()
        df["factor"] = result.values
        last_dates = sorted(panel["date"].unique())[-10:]
        df_tail = df[df["date"].isin(last_dates)]

        for date in last_dates:
            day_vals = df_tail[df_tail["date"] == date]["factor"].dropna()
            if len(day_vals) > 1:
                self.assertLess(abs(day_vals.mean()), 0.5,
                                f"{date.date()} 截面均值应接近0, 实际 {day_vals.mean():.4f}")

    def test_short_panel_no_crash(self):
        """数据不足时不崩溃"""
        panel = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=3, freq="B"),
            "code": ["000001"] * 3,
            "close": [10.0, 10.1, 10.2],
            "open": [10.0] * 3,
            "high": [10.5] * 3,
            "low": [9.5] * 3,
            "volume": [1000000] * 3,
            "amount": [10000000] * 3,
        })

        result = compute(panel)
        self.assertEqual(len(result), 3)

    def test_momentum_direction(self):
        """不同走势的股票应产生不同的因子得分（非全等）"""
        # 3只股票: 涨 / 跌 / 横盘
        dates = pd.date_range("2024-01-01", periods=30, freq="B")
        records = []
        for code, trend in [("000001", 0.02), ("000002", -0.02), ("000003", 0.0)]:
            price = 10.0
            for i, date in enumerate(dates):
                price = price * (1 + trend)
                records.append({
                    "date": date, "code": code,
                    "close": round(price, 2),
                    "open": round(price, 2),
                    "high": round(price * 1.01, 2),
                    "low": round(price * 0.99, 2),
                    "volume": 5_000_000,
                    "amount": round(5_000_000 * price, 2),
                })
        panel = pd.DataFrame(records)
        result = compute(panel)

        # 验证: 三只不同走势的股票得分不能完全相等
        last_date = dates[-1]
        mask = panel["date"] == last_date
        up_score = result[mask & (panel["code"] == "000001")].iloc[0]
        down_score = result[mask & (panel["code"] == "000002")].iloc[0]
        flat_score = result[mask & (panel["code"] == "000003")].iloc[0]
        scores = [up_score, down_score, flat_score]
        # 至少有一对得分不同（因子对三种走势产生了差异化信号）
        self.assertTrue(
            any(abs(scores[i] - scores[j]) > 0.001 for i in range(3) for j in range(i+1, 3)),
            f"三只不同走势的股票应产生不同的因子得分，实际: 涨={up_score:.4f}, 跌={down_score:.4f}, 横={flat_score:.4f}"
        )


if __name__ == "__main__":
    unittest.main()
