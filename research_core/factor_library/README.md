# Factor Library - 因子库

本模块包含复现的经典因子实现，用于量化研究。

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

输出 DataFrame 包含：
- `date`: 日期
- `code`: 股票代码
- `alpha1` - `alpha10`: 因子值

## 复现说明

- 因子公式已在本地完成验证
- 平台对照使用 JoinQuant alpha101/alpha191
- 本模块不包含任何私有数据和大结果文件

## 使用示例

```python
from research_core.factor_library import compute_wq101_alphas, compute_gtja191_alphas
from research_core.factor_library.batch_compute import compute_factor_set
from research_core.factor_library.ai_factor_mining import mine_and_validate_factors

# 计算 WQ101 因子
wq101_result = compute_wq101_alphas(df)

# 计算 GTJA191 因子
gtja191_result = compute_gtja191_alphas(df)

# 统一批量入口
subset = compute_factor_set(df, "wq101", factors=["alpha1", "alpha3", "alpha6"])

# Rule-based AI factor mining prototype
factor_panel, ic_series, summary = mine_and_validate_factors(df)
```

## 批量计算入口

`compute_factor_set(df, factor_set, factors=None)` 支持：

- `factor_set="wq101"`
- `factor_set="gtja191"`

`factors` 可选，例如 `["alpha1", "alpha3"]`。如果不传，则返回该因子集的前 10 个因子。

## 轻量有效性检验

`validation.py` 提供纯 pandas 版本的：

- `compute_forward_returns`
- `compute_ic_series`
- `summarize_ic`

这些函数不访问 SmartData、JoinQuant、BigQuant 或任何本地私有文件。

## AI Factor Mining Prototype

`ai_factor_mining.py` 提供一个 rule-based 原型，用于模拟 AI 自动生成候选因子的流程：

1. 生成候选公式元数据
2. 计算候选因子
3. 计算 forward return
4. 计算 IC
5. 输出候选因子排名

当前实现不调用外部 LLM API。后续可以将 `generate_candidate_factors()` 替换为真正的 LLM 生成器，同时保留相同的 `CandidateFactor` 接口。

运行 smoke example：

```bash
python -m research_core.factor_library.example_usage
```
