# 因子提交模板

实习生提交因子复现代码的标准化流程。

## 提交格式

在 `submissions/` 目录下创建以因子名命名的子目录，包含以下三个文件：

```
submissions/
└── my_factor_name/
    ├── factor.py        # 因子计算实现
    ├── spec.json        # 因子规格说明
    └── test_factor.py   # 单元测试（必须）
```

故意失败的负例样本不要放在 `submissions/` 下，应放到 `examples/negative_submissions/` 一类的非提交流程目录，避免 CI 将其当作真实提交因子执行。

### 1. factor.py

必须包含 `compute(panel)` 函数，接收一个 pandas DataFrame，返回一个 pandas Series。

```python
# submissions/my_factor/factor.py
import pandas as pd

def compute(panel: pd.DataFrame) -> pd.Series:
    """
    计算因子值。

    Args:
        panel: DataFrame，必须包含 date, code 列及 OHLCV 字段

    Returns:
        pd.Series，与 panel 索引对齐的因子值
    """
    # 在此实现因子逻辑
    return panel.groupby("code")["close"].pct_change(20)
```

### 2. spec.json

因子规格说明（FactorResearchSpec）：

```json
{
  "factor_name": "momentum_20d",
  "library": "custom",
  "version": "1.0.0",
  "display_name": "20日动量",
  "source_document": "原始论文或来源",
  "formula": "(P_t - P_{t-20}) / P_{t-20}",
  "description": "20日价格动量因子",
  "frequency": "day",
  "required_fields": ["close"],
  "parameters": {"window": 20},
  "tags": ["momentum", "price"]
}
```

### 3. test_factor.py

**必须**包含单元测试。使用合成数据验证公式正确性：

```python
import unittest
import pandas as pd
import numpy as np
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from factor import compute


class TestFactor(unittest.TestCase):
    def test_compute_on_synthetic_data(self):
        """用合成数据手算验证公式正确性"""
        # 构造 3 只股票 × 5 天的简化数据
        dates = pd.date_range("2024-01-01", periods=5, freq="B")
        records = []
        for code, base_price in [("000001", 10.0), ("000002", 20.0), ("000003", 30.0)]:
            for i, date in enumerate(dates):
                records.append({
                    "date": date,
                    "code": code,
                    "close": base_price * (1 + i * 0.01),
                    "open": base_price * (1 + i * 0.01 - 0.005),
                    "high": base_price * (1 + i * 0.01 + 0.01),
                    "low": base_price * (1 + i * 0.01 - 0.01),
                    "volume": 1000000,
                    "amount": 10000000,
                })

        panel = pd.DataFrame(records)
        result = compute(panel)

        # 验证因子值
        self.assertEqual(len(result), len(panel))
        self.assertTrue(result.notna().sum() > 0,
                        "因子至少应产生一些有效值")

    def test_no_crash_on_edge_cases(self):
        """边界情况不崩溃"""
        panel = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=2, freq="B"),
            "code": ["000001", "000001"],
            "close": [10.0, 10.0],
            "open": [10.0, 10.0],
            "high": [10.1, 10.1],
            "low": [9.9, 9.9],
            "volume": [0, 1000000],
            "amount": [0, 10000000],
        })

        # 不应崩溃
        result = compute(panel)
        self.assertEqual(len(result), 2)


if __name__ == "__main__":
    unittest.main()
```

## 验证流程

提交 PR 后，GitHub Actions 会自动运行：

1. **Layer 1 (公式正确性)**: 运行 test_factor.py 单元测试
2. **Layer 2 (数据验证)**: 检查字段映射、样本点生成、覆盖率
3. **Layer 3 (外部真值)**: 如有真值 CSV，自动截面对照
4. **有效性评估**: 计算 Rank IC、ICIR、Long-Short 收益

验证报告会自动作为 PR 评论贴出。

## 常见错误和解决

| 错误 | 原因 | 解决 |
|------|------|------|
| `coverage_ratio = 0` | 因子全为空值 | 检查 window 参数是否超出数据长度 |
| `rank_ic_mean = NaN` | 缺少 forward_return 列 | 确保 panel 包含 close 列 |
| `field_mapping_match = failed` | 缺失必需字段 | 检查 spec.json 的 required_fields |
| 因子值全为常数 | 公式逻辑错误 | 用 test_factor.py 中的合成数据逐行 debug |
