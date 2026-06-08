# Factor Library Compatibility Layer - 因子库兼容层

本模块保留旧调用路径，但新增因子能力的正式主线已经接入 `research_core/factor_lab/`。

新代码应优先使用：

```python
from research_core.factor_lab.libraries.factor_sets import (
    compute_factor_set,
    compute_gtja191_alphas,
    compute_wq101_alphas,
)
```

CLI / proof / report 链路应优先使用：

```bash
python -m research_core.factor_lab.cli run-factor-set-demo --factor-set gtja191
python -m research_core.factor_lab.cli run-factor-set-demo --factor-set wq101
```

## 支持的因子

### WorldQuant Alpha101 (WQ101)
- Alpha#1 - Alpha#10
- 来源: WorldQuant "101 Formulaic Alphas" Appendix A

### GTJA191
- Alpha#1 - Alpha#10
- 来源: 国泰君安《基于短周期价量特征的多因子选股体系》Table 6

## 输入数据格式

要求输入 DataFrame 包含以下列：
- `date`: 日期
- `code`: 股票代码
- `open`: 开盘价
- `high`: 最高价
- `low`: 最低价
- `close`: 收盘价
- `volume`: 成交量
- `amount`: 成交额

## 输出数据格式

兼容层输出 DataFrame 包含：
- `date`: 日期
- `code`: 股票代码
- `alpha1` - `alpha10`: 因子值

## 复现说明

- `research_core.factor_library` 仅作为兼容层，内部调用 `research_core.factor_lab` 的正式实现。
- WQ101 Alpha#1-#10 直接调用 `factor_lab` 当前 Alpha101 主线实现，避免维护两套逻辑后分叉。
- GTJA191 Alpha#1-#10 已有 `factor_lab` specs、registry、service、truth、proof、report、CLI 入口。
- 本仓库内的 `example_usage` 只使用 mock data 做 smoke test，不能作为真实市场复现证明。
- 真实数据验收摘要见 `docs/FACTOR_LIBRARY_REAL_DATA_EVIDENCE.md`。
- 平台对照使用 JoinQuant alpha101/alpha191，但全市场 IC 对照仍属于二级待补验证。
- 本模块不包含任何私有数据和大结果文件。

## 使用示例

```python
from research_core.factor_lab.libraries.factor_sets import (
    compute_factor_set,
    compute_gtja191_alphas,
    compute_wq101_alphas,
)

# 计算 WQ101 因子
wq101_result = compute_wq101_alphas(df)

# 计算 GTJA191 因子
gtja191_result = compute_gtja191_alphas(df)

# 统一批量入口
subset = compute_factor_set(df, "wq101", factor_names=["alpha1", "alpha3", "alpha6"])
```

## 批量计算入口

正式主线 `compute_factor_set(df, factor_set, factor_names=None)` 支持：

- `factor_set="wq101"`
- `factor_set="gtja191"`

`factor_names` 可选，例如 `["alpha1", "alpha3"]`。如果不传，则返回该因子集的前 10 个因子。

兼容层 `research_core.factor_library.batch_compute.compute_factor_set(df, factor_set, factors=None)` 仍可使用；`batch_compute_factors()` 会按实际返回列动态加前缀，例如 `wq101_alpha1`、`gtja191_alpha10`。

## 轻量有效性检验

`validation.py` 提供纯 pandas 版本的：

- `compute_forward_returns`
- `compute_ic_series`
- `compute_monthly_ic`
- `summarize_ic`

这些函数不访问 SmartData、JoinQuant、BigQuant 或任何本地私有文件。

`compute_forward_returns()` 输出字段为 `forward_return`。`compute_monthly_ic()` 默认读取同名字段；如果需要兼容旧数据表中的 `return` 字段，必须显式传入 `return_col="return"`。

运行 smoke example：

```bash
python -m research_core.factor_library.example_usage
```

该命令只证明包导入、因子计算、批量入口和候选因子排序流程能跑通。真实 Alpha101 / Alpha191 复现证明必须使用真实行情、因子输出、无前视偏差对齐和外部参考对照，不能只依赖 mock example。
