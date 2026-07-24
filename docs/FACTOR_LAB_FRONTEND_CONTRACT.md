# Factor Lab Frontend Contract

本文档定义 Factor Lab 前端读取后端数据的统一格式。目标是让前端、skills、策略模块、人工审核和未来云端同步都能围绕同一个输出契约协作，避免每个人各写一套 JSON。

## 核心原则

1. 前端不直接依赖核心计算内部函数。
2. 前端不直接拼本机绝对路径。
3. 核心程序的原始产物可以保留，前端读取统一 view model。
4. 修改核心逻辑时，只要最终能生成这个契约，前端就不需要跟着大改。

## 数据来源边界

因子清单通过“因子来源”统一收集。当前已经实现的来源是：

```text
research_core/factor_lab/libraries/*/specs.py
```

这里是手写/代码库内置因子的稳定声明层，用来告诉前端“有哪些因子”。前端不直接扫描 `factors.py`，因为 `factors.py` 是计算实现层，可能包含 helper、动态逻辑和策略研究代码。

未来动态产生的因子，例如：

```text
文献爬取得到的候选因子
多因子合成产生的候选因子
自动挖掘 agent 发现的候选因子
外部同事或外部 agent 提交的候选因子
```

不建议直接写进 `specs.py`。这些因子应该先进入“数据定义的因子注册表”，例如未来的：

```text
runtime/factor_lab/registries/*.json
cloud_factor_registry
company_factor_registry
```

然后由新的 factor source 接入前端 view model。这样 `specs.py` 继续表示代码库内置因子，动态因子由数据注册表管理，二者不会混在一起。

运行状态、验证结果和指标来自：

```text
runtime/factor_lab/reports/*_proof_report.json
```

也就是说：

```text
specs.py = 因子目录
factor registry = 动态因子目录
factors.py = 后端计算实现
runtime/factor_lab = 运行后的结果和产物
factor_lab_web = 给前端看的只读适配层
```

如果某个因子来源加载失败，例如某个 `specs.py` import 出错或 `specs()` 执行失败，适配层会继续处理其它来源，但必须暴露 warning：

```text
metadata.factor_source_warning_count
errors[].code = FACTOR_SOURCE_WARNING
```

这样不会因为一个库出错导致整个页面崩掉，也不会让失败的库悄悄消失。

## 统一结构

```json
{
  "schema_version": "factor_lab_view_v1",
  "generated_at": "2026-06-24T10:00:00Z",
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

## 字段说明

### schema_version

当前固定为：

```text
factor_lab_view_v1
```

后续如果字段结构发生不兼容变化，新增 `factor_lab_view_v2`，不要悄悄改旧格式。

### factor

描述因子本身。

```json
{
  "factor_id": "WQ101:alpha1",
  "factor_name": "alpha1",
  "raw_factor_name": "alpha1",
  "library": "WQ101",
  "category": "量价因子",
  "category_inferred": false,
  "subcategory": "动量",
  "required_fields": ["returns", "close"],
  "metadata": {
    "category_inferred": false
  }
}
```

Field naming contract:

- `factor_id` is the stable query ID used by the frontend and detail API. It should use `<library>:<raw_factor_name>`.
- `factor_name` is the display name used by the frontend. If two libraries share the same raw name, the adapter may use a declared `factor_id` as the display name, for example GTJA191 raw `alpha1` can display as `gtja191_alpha_001`.
- `raw_factor_name` is the original name used by core computation, proof/truth comparison, and runtime artifacts. Do not rename it for display-only reasons.

`category` 应优先由因子在 `specs.py` 或未来 factor registry 中显式声明，例如：

```text
量价因子 / 技术因子 / 财务因子 / 规模因子 / 价值因子 / 自定义因子
```

当前建议 category 使用以下固定枚举，避免前端分类标签和后端声明不一致：

```text
量价因子
技术因子
财务因子
规模因子
价值因子
自定义因子
```

如果未来需要新增“情绪因子”“另类数据因子”等分类，应先同步更新契约和前端分类配置，而不是在单个 specs.py 中临时发明新 category。

适配层会保留最后兜底推断逻辑，但这只用于缺少声明的老因子或临时因子。凡是通过兜底逻辑得到的分类，都会标记：

```text
category_inferred: true
```

这表示分类是适配层猜出来的，不是因子定义自己声明的，后续应该补真实分类。

当前 `build_factor_view` 可以同时接受展示库名和部分原始库名，例如 `WQ101:alpha1` 与 `Alpha101:alpha1` 都会归一化后查询。长期建议前端和外部调用统一使用带库名前缀的 factor_id，不要传无前缀因子名。

### job

描述最近一次复现或验证任务。

```json
{
  "job_id": "alpha101-c015efeba388",
  "status": "completed",
  "library": "Alpha101",
  "generated_at": "2026-06-17T01:27:28Z",
  "data_source": "demo",
  "truth_enabled": true,
  "dataset": {}
}
```

### validation

描述复现和 truth 对比结论。

```json
{
  "proof_status": "passed",
  "truth_status": "exact_match",
  "overall_status": "passed",
  "truth_exact_match_ratio": 1.0,
  "truth_max_abs_error": 0.0
}
```

建议状态枚举：

```text
proof_status: passed / failed / partial / pending / missing
truth_status: exact_match / mismatch / not_applicable / not_compared / pending / empty_compare / missing
overall_status: passed / failed / partial / pending / review_needed
```

`overall_status` is factor-level status for the current row/detail view. It must not be copied from `report.summary.overall_status`, because that summary field describes the whole job batch. The adapter should either derive factor-level `overall_status` from that factor's own `proof_status` and `truth_status`, or omit it when no reliable factor-level status exists.

`truth_status` 的语义必须区分清楚，不能把所有“没有匹配结果”的情况都显示成同一种“无对照”：

```text
exact_match
  完全匹配。有标准 truth，且 proof 结果与 truth 对上。

mismatch
  不匹配。有标准 truth，但 proof 结果与 truth 不一致，需要关注。

not_applicable
  无需对照。这个因子本身没有标准 truth 可对，例如未来 AI 挖掘、文献爬取或多因子合成产生的全新因子。
  这不是“还没对照”，而是“这类因子天生不靠 truth 验证”。
  对这类因子，前端应同时展示 proof_status、coverage_ratio、IC/IR、分层表现等有效性指标，
  让用户知道它应通过复现完整性和研究有效性判断，而不是通过 truth_exact_match_ratio 判断。

not_compared / pending
  待对照。这个因子有 truth，理论上应该对照，但当前还没有跑 truth 对比。

empty_compare
  对照异常。truth 对比流程运行了，但结果为空，通常表示流程或输入数据异常，需要关注。

missing
  缺失。本该存在的 truth 对照数据或对照产物丢失。
```

前端展示建议：

```text
not_applicable 显示为“无需对照”，不要显示成“未对比”。
not_compared / pending 显示为“待对照”。
empty_compare 显示为“对照异常”。
missing 显示为“缺失”。
```

### metrics

描述当前已有的研究级指标。

```json
{
  "coverage_ratio": 0.982,
  "rank_ic_mean": 0.052,
  "rank_ic_ir": 0.48,
  "long_short_mean": 0.0012
}
```

注意：这些指标不等于正式策略收益。正式策略收益需要策略层结合交易成本、滑点、调仓、风控后计算。

### research

预留给单因子研究分析。

当前可以返回：

```json
{
  "status": "not_available",
  "reason": "waiting_for_research_analysis_backend",
  "params": {},
  "ic_summary": null,
  "ic_series": [],
  "stratification_curves": [],
  "group_performance": []
}
```

未来接入真实研究分析后，建议输出 `research_analysis.json`，包含：

```text
params
data_quality
ic_summary
ic_series
stratification_curves
group_performance
industry_ic
```

### artifacts

描述产物文件。这里必须区分两个概念：

```text
artifact_status: 文件是否生成
validation_status: 这个文件代表的验证结论是否通过
```

示例：

```json
{
  "kind": "proof",
  "name": "proof.json",
  "label": "single_factor_proof",
  "artifact_status": "generated",
  "validation_status": "failed",
  "url": "/api/agents/factor-lab/artifacts/alpha101-c015efeba388/proof?factor=alpha84"
}
```

这可以避免“文件已生成但验证失败”被前端误显示成全绿。

### errors

描述硬错误或需要人工关注的问题。

```json
[
  {
    "code": "TRUTH_NOT_EXACT_MATCH",
    "status": "mismatch"
  }
]
```

### metadata

描述 view 的生成来源、数据来源和兼容说明。

```json
{
  "view_source": "factor_lab_web_adapter",
  "data_source": "demo",
  "display_library_alias": "WQ101 maps to the current Alpha101 implementation."
}
```

## 推荐接口

```text
GET /api/agents/factor-lab/factor-library
GET /api/agents/factor-lab/factors/<factor_id>/view
GET /api/agents/factor-lab/factors/<factor_id>/research-analysis/latest
GET /api/agents/factor-lab/jobs/<job_id>/artifacts
GET /api/agents/factor-lab/artifacts/<job_id>/<artifact_kind>
GET /api/agents/factor-lab/health
```

## 给新增模块的要求

不管后续同事写的是 skill、agent、策略、研究分析还是回测，建议最终都能提供：

```text
job_id
status
artifacts
metrics
errors
metadata
```

这样云端同步、人工审核、前端看板和运行监控都能统一管理。
