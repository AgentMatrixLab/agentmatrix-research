# Factor Lab Web Adapter

这个目录是给前端使用的只读适配层。它不负责因子计算、不负责 truth 生成、不负责 proof 判定，也不负责策略回测；它只读取核心程序已经生成的产物，并整理成前端稳定读取的 JSON。

## 为什么要有这一层

Factor Lab 现在还在快速迭代，同事可能会继续修改 skills、因子库、策略和核心复现流程。如果前端直接读取 `proof.json`、`evaluation.json`、`truth_compare.json`、`proof_report.json`、`factor_frame.csv` 等零散文件，后面字段和路径一变，页面就会跟着坏。

所以前端只依赖一个统一契约：

```text
factor_lab_view_v1
```

核心程序可以继续变化，但只要这一层还能把输出整理成 `factor_lab_view_v1`，前端就可以保持稳定。

## 目录职责

```text
repository.py
读取 runtime/factor_lab 下已有 JSON 和 job 列表。

factor_sources.py
定义“因子来源”扩展点。当前只实现 specs.py 来源，未来可以增加 JSON 注册表、云端注册表等来源。

artifact_service.py
统一管理 artifact 的安全路径解析和前端 URL。

view_model.py
把 job、proof、truth、report、metrics 整理成前端统一 view JSON。
```

## 当前读取来源

因子清单通过 factor source 收集。当前启用的来源只有：

```text
research_core/factor_lab/libraries/*/specs.py
```

`specs.py` 负责声明因子元信息，例如 `factor_name`、`library`、`category`、`subcategory`、`required_fields`、`formula` 和 `description`。

如果某个 `specs.py` 加载失败、`specs()` 执行失败，或者返回结构不符合预期，适配层会记录 warning 日志，并在 view 中暴露：

```text
metadata.factor_source_warning_count
errors[].code = FACTOR_SOURCE_WARNING
```

失败来源会被跳过，但不会静默消失。

因子应尽量显式声明 `category`。如果缺少声明，适配层会用 library、tags 和 required_fields 做最后兜底推断，并在因子 metadata 中标记：

```text
category_inferred: true
```

这类因子后续应补充真实分类，不建议长期依赖兜底推断。

当前建议 `category` 使用固定枚举：

```text
量价因子
技术因子
财务因子
规模因子
价值因子
自定义因子
```

如果未来新增分类，应同步更新契约和前端分类配置。

运行状态和指标只从已经生成的 runtime/report 产物中补充：

```text
runtime/factor_lab/reports/*_proof_report.json
```

前端不会直接扫描 `factors.py`。`factors.py` 仍然只用于后端复现、研究分析和策略计算。

未来动态产生的因子，例如文献爬取、多因子合成、自动挖掘或外部 agent 提交的候选因子，不应该直接写入 `specs.py`。建议通过数据定义的因子注册表接入，例如：

```text
runtime/factor_lab/registries/*.json
cloud_factor_registry
company_factor_registry
```

到时只需要新增一个 factor source，并在 `configured_factor_sources()` 中启用；`view_model.py` 的主流程不需要重构。

## 前端统一读取格式

单因子详情建议读取：

```text
GET /api/agents/factor-lab/factors/<factor_id>/view
```

返回结构：

```json
{
  "schema_version": "factor_lab_view_v1",
  "factor": {},
  "job": {},
  "validation": {},
  "metrics": {},
  "research": {},
  "artifacts": [],
  "errors": [],
  "metadata": {}
}
```

## 给同事新增 skills / 策略 / 因子的约定

新增任何能力时，建议至少保证最终能落到下面这些字段中：

```text
job_id
factor_id
factor_name
library
status
artifacts
metrics
errors
metadata
```

如果是新的 factor skill，建议提供：

```text
factor_id
factor_name
library
category
subcategory
required_fields
formula 或 description
```

如果是新的复现或验证流程，建议提供：

```text
proof_status
truth_status
overall_status
truth_exact_match_ratio
truth_max_abs_error
coverage_ratio
rank_ic_mean
rank_ic_ir
```

`overall_status` 是单因子视图里的状态，不能直接使用 `report.summary.overall_status`。`summary.overall_status` 描述的是整批 job 的汇总结论；单个因子的 `overall_status` 应基于该因子的 `proof_status` 和 `truth_status` 推导，或者在没有可靠单因子状态时不输出。

`truth_status` 建议统一使用以下语义：

```text
exact_match
  完全匹配：有标准 truth，且复现结果与 truth 对上。

mismatch
  不匹配：有标准 truth，但复现结果与 truth 不一致。

not_applicable
  无需对照：因子本身没有标准 truth 可对，例如未来 AI 挖掘、文献爬取或多因子合成产生的全新因子。
  这类因子不应被理解成“还没对照”，应结合 proof_status、coverage_ratio、IC/IR 和研究分析指标判断。

not_compared / pending
  待对照：因子有 truth，应该对照，但当前还没跑 truth 对比。

empty_compare
  对照异常：truth 对比流程运行了，但结果为空，需要关注。

missing
  缺失：本该存在的 truth 对照数据或对照产物丢失。
```

如果是新的策略或研究分析流程，建议输出单独的：

```text
research_analysis.json
```

至少包含：

```text
params
ic_summary
ic_series
stratification_curves
group_performance
data_quality
```

策略回测不要混进当前复现 proof 里，建议以后单独走：

```text
backtest_result.json
```

## 重要边界

这一层可以改：

```text
字段映射
显示用状态归一化
artifact URL
缺失文件兜底
前端 view JSON 结构
```

这一层不应该改：

```text
因子公式
因子计算结果
truth 对比算法
proof 通过/失败判断
evaluation 评分逻辑
策略回测收益计算
```

一句话原则：核心程序负责“算出结果”，这个目录负责“把结果稳定地给前端看”。
