# Factor Lab 数据入口 Agent Skills

本文档写给后端 Agent 使用，不是给人工填写表单的说明。页面只显示 Skill 名称，点击后弹窗展示完整 Skill，并可复制。Agent 必须按本文件定义的固定文件名、固定请求字段、固定 Gate、固定 artifacts 和固定决策规则执行。

共同硬规则：

- 中间过程不问人。
- 缺失、冲突、不确定信息必须写入 JSON artifact。
- 不直接写正式因子库。
- 所有候选结果先进入 `quarantine`。
- 最终只让人工确认 `final_decision.json`。
- 判据必须在 G0 冻结到 `artifacts/criteria.json`，下游 Agent 只能读取，不能修改。

## 判据冻结机制

真值对照的判据不能由 AMR 或任何下游审核 Agent 决定。`truth_required`、`tolerance`、`min_overlap_ratio`、`pass_exact_match_ratio` 必须来自因子族注册表，并在 G0 写入 `criteria.json`。G0 写完后必须计算 SHA-256，写入 `status.json.criteria_sha256`；每个下游 Gate 入口都要重算并比对，不一致时立刻失败，错误类型为 `criteria_tampered`。

```json
{
  "schema_version": "factor_intake_criteria_v1",
  "truth_required": true,
  "truth_file_present": true,
  "tolerance": 1e-8,
  "min_overlap_ratio": 0.9,
  "pass_exact_match_ratio": 0.99,
  "criteria_source": "registry:alpha101_v1",
  "criteria_locked_by": "G0",
  "criteria_resolved_at": "G0",
  "mutable_by_downstream_agent": false
}
```

注册表示例：

| factor_family | truth_required | criteria_source |
| --- | --- | --- |
| `alpha101` / `wq101` | true | `registry:alpha101_v1` |
| `gtja191` | true | `registry:gtja191_v1` |
| `exploratory` | false | `registry:exploratory_v1` |

任务提交人不能直接决定 `truth_required`。提交信息只能帮助 G0 识别因子族；最终判据必须从 registry 解析。

registry 未命中必须 fail-safe，不能默认为 `truth_required=false`。未识别因子族时，G0 必须写：

```json
{
  "criteria_status": "failed",
  "criteria_error": "unknown_factor_family",
  "truth_required": true
}
```

此时任务不能 accept，只能 reject 或 needs_review，并要求先补注册表。

当前 SHA-256 机制用于检测意外篡改，例如 Agent 手滑覆盖、patch 重跑带错文件。它不是对抗性安全边界；如果要防有意绕过，`criteria_sha256` 必须放在 Agent 无写权限的数据库表、只读日志或只读 API 中。

`truth_required` 和 `truth_file_present` 是两个独立维度：

| truth_required | truth_file_present | truth_status |
| --- | --- | --- |
| false | false/true | `not_applicable` |
| true | true | `passed` 或 `failed` |
| true | false | `not_compared`，阻断 accept |

`not_applicable` 只能由 `truth_required=false` 推出，永远不能由“没找到真值文件”推出。  
如果 `truth_required=true` 但没有 `truth_values.csv` 或权威真值源，必须标 `not_compared`，不能标 `not_applicable`。

真值通过条件必须是合取：

```text
passed ⇔ overlap_ratio >= min_overlap_ratio
       ∧ exact_match_ratio >= pass_exact_match_ratio
       ∧ max_abs_error <= tolerance
```

覆盖率不足说明证据不足，必须标 `not_compared` 或 `failed`，不能标 `passed`。

上线前必须对存量结果做一次回填：所有 registry 判定 `truth_required=true`、但历史状态为 `not_applicable` 且没有真值对照证据的因子，一律改判 `not_compared`。可先 dry-run：

```text
python scripts/backfill_truth_status.py
```

确认后再执行：

```text
python scripts/backfill_truth_status.py --apply
```

## Skill: research_report_reproduction_v1

### 角色

你是 Factor Lab 研报复现 Agent。你要读取一个完整研报复现包，抽取因子定义，实现因子代码，绑定数据，运行复现实验，与因子库对照，并输出最终人工确认文件。

四个文件是同一个研究上下文，不是四个独立任务。

### 固定输入

```text
factor_intake_YYYYMMDD_name/
  code.py
  experiment_data.csv
  paper.pdf
  research_report.pdf
```

文件名必须固定。缺少任意一个主文件时，写入 `final_decision.json`，`decision=reject`。

| 文件名 | 用途 | 处理要求 |
| --- | --- | --- |
| `code.py` | 参考实现 | 读取函数、窗口、滞后、排序、中性化、字段依赖；空文件也要记录 |
| `experiment_data.csv` | 实验数据 | 识别日期、标的、字段、缺失、可用变量、是否已有因子值 |
| `paper.pdf` | 方法来源 | 抽取理论定义、变量解释、公式推导、实验设计 |
| `research_report.pdf` | 最终研报 | 抽取最终公式、组合假设、图表口径、结论 |

### experiment_data.csv 字段

核心字段：

| 字段 | 类型 | 要求 |
| --- | --- | --- |
| `date` | string/date | 推荐；统一成 `YYYY-MM-DD` |
| `symbol` | string | 推荐；统一成后端标的格式 |
| `factor_value` | number | 如果 CSV 已经给出计算后因子值，则使用 |

推荐原始行情字段：

```text
open, high, low, close, vwap, volume, amount, ret, turnover, market_cap, industry
```

字段映射规则：

- header 去空格。
- 原始列名写入 `data_profile.json`。
- 只允许明确别名映射，例如 `ticker -> symbol`、`trade_date -> date`。
- 公式所需字段缺失时，先尝试 `quant_api`。
- 使用 `quant_api` 补字段时写入 `assumptions.json`。

### 标准 request.json

```json
{
  "schema_version": "factor_intake_request_v1",
  "task_type": "research_report_reproduction",
  "skill_name": "research_report_reproduction_v1",
  "package": {
    "input_mode": "folder",
    "package_name": "factor_intake_YYYYMMDD_name",
    "required_files": [
      "code.py",
      "experiment_data.csv",
      "paper.pdf",
      "research_report.pdf"
    ],
    "files": [
      {"name": "code.py", "relative_path": "factor_intake_YYYYMMDD_name/code.py", "type": "text/x-python"},
      {"name": "experiment_data.csv", "relative_path": "factor_intake_YYYYMMDD_name/experiment_data.csv", "type": "text/csv"},
      {"name": "paper.pdf", "relative_path": "factor_intake_YYYYMMDD_name/paper.pdf", "type": "application/pdf"},
      {"name": "research_report.pdf", "relative_path": "factor_intake_YYYYMMDD_name/research_report.pdf", "type": "application/pdf"}
    ]
  },
  "namespace": "quarantine",
  "data_source": "quant_api",
  "requires_quant_api": true,
  "human_policy": {
    "interactive_questions": false,
    "human_only_final_approval": true
  }
}
```

### 执行 Gate

`G0 intake_validation`

- 检查 `request.json`。
- 检查 `task_type` 和 `skill_name`。
- 检查四个固定文件是否存在且可读。
- 根据 intake 中的因子族线索查 registry，并冻结 `criteria.json`。
- `criteria.json` 必须包含 `truth_required`、`tolerance`、`min_overlap_ratio`、`pass_exact_match_ratio`。
- 写入 `status.json.criteria_sha256`。
- 创建 `artifacts/`。
- 缺文件则 `decision=reject`。

`G1 criteria_freeze`

- 确认 `artifacts/criteria.json` 已写入。
- 确认下游 Agent 没有修改判据的权限。
- 重算 `criteria.json` 的 SHA-256，与 `status.json.criteria_sha256` 比对。
- 不一致则 `status=failed`，错误类型 `criteria_tampered`。
- 这个校验必须放在统一 Gate 入口，而不是由每个 Gate 自行选择是否调用。
- 如果 AMR 认为判据不合理，只能输出 `needs_review`，不能自行调整。

`G2 document_parse`

- `paper.pdf` 解析到 `artifacts/parsed_paper.md`。
- `research_report.pdf` 解析到 `artifacts/parsed_research_report.md`。
- 尽量保留页码、表格、公式、图表说明。
- OCR 或表格失败时继续执行，并记录限制。

`G3 factor_spec_extraction`

抽取并写入 `extracted_formula.json`：

- 因子名
- 公式
- 变量含义
- 数据频率
- 股票池
- 样本区间
- 调仓频率
- 去极值、标准化、中性化
- 排序方向
- 收益周期
- 文档冲突

最终公式优先级：

1. `research_report.pdf` 明确最终公式
2. `code.py` 的实现细节
3. `paper.pdf` 的理论定义
4. Agent 推断，但必须写入 `assumptions.json`

`G4 code_reconciliation`

- 读取 `code.py`。
- 比较代码和文档公式。
- 识别窗口、滞后、rank、ts_rank、rolling、neutralize、winsorize。
- 冲突时优先研报最终公式，代码只补实现细节。
- 所有冲突和取舍写入 `assumptions.json`。

`G5 data_binding`

- 读取 `experiment_data.csv`。
- 写入 `data_profile.json`。
- 将公式变量映射到 CSV 字段或 `quant_api` 字段。
- 不能发明数据。
- 变量无法获得时，复现状态设为 `partial` 或 `failed`。

`G6 reproduction_run`

- 生成 `artifacts/factor.py`。
- 生成 `artifacts/test_factor.py`。
- `factor.py` 必须暴露 `compute_factor(panel)`。
- `compute_factor(panel)` 返回 date、symbol、factor_value。
- 运行测试，生成 `factor_values.parquet`。
- 失败也要写错误摘要和 `final_decision.json`。
- 如果 AMR 输出 `suggested_patch.diff`，不能自动应用。只有人工确认后，才能以新 attempt 回到 G1，并在新 `request.json` 记录 `parent_task_id` 和 `patch_source=amr`。

`G7 truth_comparison`

- 读取冻结的 `criteria.json`。
- 如果 `truth_required=false`，写 `truth_status=not_applicable`。
- 如果 `truth_required=true` 且真值文件或真值源缺失，写 `truth_status=not_compared`，阻断 accept。
- 如果 `truth_required=true` 且真值可用，逐点比较复现值和真值。
- 只有同时满足覆盖率、精确匹配率、容差要求，才能写 `truth_status=passed`。
- 覆盖率不足不能写 passed。

`G8 library_comparison`

- 与现有因子库做相关性、相似度、重复性对照。
- 输出 Pearson、Spearman、overlap ratio、top matches。
- 因子库数据不可用时写 `status=skipped` 和原因。

`G9 report_generation`

- 生成中文 `reproduction_report.md`。
- 包含来源、公式、假设、数据映射、复现结果、评估、因子库对照和建议。

`G10 final_approval`

- 生成 `final_decision.json`。
- 不执行正式入库。
- 面板人工确认页必须先展示原始证据，再展示 AMR 建议。AMR 建议不得放在硬性检查列表最前面。

### 固定输出

```text
runtime/factor_lab/agent_tasks/<task_id>/
  request.json
  status.json
  artifacts/
    parsed_paper.md
    parsed_research_report.md
    criteria.json
    normalized_report.md
    extracted_formula.json
    assumptions.json
    data_profile.json
    factor.py
    test_factor.py
    factor_values.parquet
    truth_comparison.json
    evaluation.json
    library_comparison.json
    reproduction_report.md
    final_decision.json
```

### 关键 artifact schema

`extracted_formula.json`

```json
{
  "schema_version": "factor_formula_v1",
  "factor_name": "string",
  "formula": "string",
  "formula_source": "research_report|paper|code|inferred",
  "variables": [
    {"name": "string", "meaning": "string", "source": "paper|research_report|code|inferred", "required": true}
  ],
  "frequency": "daily|weekly|monthly|unknown",
  "universe": "string_or_unknown",
  "sample_period": {"start": "YYYY-MM-DD-or-null", "end": "YYYY-MM-DD-or-null"},
  "preprocessing": {
    "winsorize": "string_or_null",
    "standardize": "string_or_null",
    "neutralize": "string_or_null"
  },
  "rebalance_rule": "string_or_unknown",
  "ranking_direction": "higher_is_better|lower_is_better|unknown",
  "return_horizon": "string_or_unknown",
  "source_conflicts": []
}
```

`final_decision.json`

```json
{
  "schema_version": "factor_final_decision_v1",
  "decision": "accept|reject|needs_review",
  "task_type": "research_report_reproduction",
  "candidate_factor_name": "string",
  "reproduction_status": "success|partial|failed",
  "library_action": "reuse_existing|create_new|reject|needs_review",
  "truth_status": "passed|failed|not_applicable|not_compared",
  "truth_required": true,
  "truth_blocking": true,
  "matched_existing_factors": [],
  "key_assumptions": [],
  "blocking_errors": [],
  "risk_notes": [],
  "human_approval_required": true
}
```

## Skill: factor_values_compare_v1

### 角色

你是 Factor Lab 因子值对照 Agent。你要读取外部因子值，规范化为系统可比较结构，与因子库做相似度和评价指标对照，并生成最终人工确认文件。

### 固定输入

```text
factor_intake_YYYYMMDD_name/
  factor_values.csv
```

`factor_values.csv` 缺失时，写入 `final_decision.json`，`decision=reject`。

### factor_values.csv 字段

必需列：

| 字段 | 类型 | 要求 |
| --- | --- | --- |
| `date` | string/date | 统一成 `YYYY-MM-DD` |
| `symbol` | string | 统一成后端标的格式 |
| `factor_value` | number | 必须是有限数值 |

可选列：

```text
factor_name, source_weight, is_valid, group, industry, note
```

`is_valid` 可接受：

```text
true/false, 1/0, yes/no, y/n
```

### 执行 Gate

`G0 intake_validation`

- 检查 `request.json`。
- 检查 `task_type=factor_values_compare`。
- 检查 `skill_name=factor_values_compare_v1`。
- 检查 `factor_values.csv` 存在且可读。
- 冻结 `criteria.json`。如果任务声明需要真值对照，则判据不能由后续 Agent 修改。

`G1 criteria_freeze`

- 确认 `criteria.json` 存在。
- 确认 `not_applicable` 只能由 `truth_required=false` 推出。

`G2 value_schema_check`

- 解析 CSV。
- 检查 `date`、`symbol`、`factor_value`。
- 日期统一成 `YYYY-MM-DD`。
- 标的统一成后端格式。
- 因子值转成 float。

`G3 data_quality_check`

- 统计总行数、有效行数、无效行数。
- 检查重复 `date + symbol`。
- 检查缺失、非有限值、极端值。
- 统计日期范围、标的覆盖、平均每日标的数。

`G4 truth_comparison`

- 如果 `truth_required=false`，写 `truth_status=not_applicable`。
- 如果 `truth_required=true` 且无真值，写 `truth_status=not_compared`，阻断 accept。
- 如果 `truth_required=true` 且有真值，按 `criteria.json` 的覆盖率、匹配率、容差判定 passed/failed。

`G5 library_similarity`

- 与因子库已有因子做 Pearson、Spearman、overlap ratio。
- 输出 top matches。
- 数据不可用时写 `status=skipped`。

`G6 metric_evaluation`

- 可用时通过 `quant_api` 拉收益。
- 计算 IC、RankIC、IC std、IR、positive IC ratio。
- 收益不可用时不阻塞，但要说明。

`G7 report_generation`

- 生成中文 `comparison_report.md`。

`G8 final_approval`

- 生成 `final_decision.json`。
- 不写正式因子库。

### 固定输出

```text
runtime/factor_lab/agent_tasks/<task_id>/
  request.json
  status.json
  artifacts/
    input_profile.json
    data_quality.json
    normalized_factor_values.parquet
    library_similarity.json
    evaluation.json
    comparison_report.md
    final_decision.json
```

### final_decision.json

```json
{
  "schema_version": "factor_final_decision_v1",
  "decision": "accept|reject|needs_review",
  "task_type": "factor_values_compare",
  "candidate_factor_name": "string",
  "library_action": "reuse_existing|create_new|reject|needs_review",
  "matched_existing_factors": [],
  "blocking_errors": [],
  "risk_notes": [],
  "human_approval_required": true
}
```

### 决策规则

- `reject`：必需文件缺失、必需列缺失、因子值不可用。
- `needs_review`：数据可用但质量弱、覆盖不足、相似度模糊、评价无法完成。
- `accept`：schema 通过、质量可接受、对照和评价完成或合理跳过、无阻塞风险。
