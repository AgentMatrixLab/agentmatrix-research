"""
Buggy reversal因子单元测试 — 会 FAIL。

验证: 公式正确但代码实现方向反了 → 单元测试应捕获
"""
import unittest
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from factor import compute


class TestBuggyReversal(unittest.TestCase):
    def test_reversal_direction(self):
        """反转因子应对上涨股票给负值"""
        dates = pd.date_range("2024-01-01", periods=10, freq="B")
        records = []
        # 股票A: 持续上涨 (10→14.5)
        # 股票B: 持续下跌 (20→15.5)
        for code, base, trend in [("A", 10.0, 0.05), ("B", 20.0, -0.05)]:
            close = base
            for i, date in enumerate(dates):
                close = base * (1 + trend * i)
                records.append({
                    "date": date, "code": code,
                    "close": close,
                    "open": close, "high": close, "low": close,
                    "volume": 1000000, "amount": 10000000,
                })

        panel = pd.DataFrame(records)
        result = compute(panel)

        # 股票A的因子值（index=5, i=5, close=10*1.25=12.5, close_t-5=10, return=0.25）
        a_val = result[(panel["code"] == "A")].iloc[5]
        # 股票B的因子值（i=5, close=20*0.75=15, close_t-5=20, return=-0.25）
        b_val = result[(panel["code"] == "B")].iloc[5]

        # 反转因子: 上涨股票应该为负值，下跌股票应该为正值
        # 但 buggy 版本方向写反了 → 此断言会失败
        self.assertLess(a_val, 0,
                        f"上涨股票A的因子值应为负（反转），实际: {a_val:.4f}")
        self.assertGreater(b_val, 0,
                           f"下跌股票B的因子值应为正（反转），实际: {b_val:.4f}")


if __name__ == "__main__":
    unittest.main()
