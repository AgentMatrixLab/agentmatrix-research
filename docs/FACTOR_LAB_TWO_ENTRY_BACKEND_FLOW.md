# Factor Lab Two-Entry Backend Flow

本文档定义当前后端入口重塑后的两个任务路径。核心原则：

- 真值对照只作为第一类任务的主判据。
- 研报论文复现不强制要求标准真值；如果有真值，只做诊断和归因。
- Agent 不需要 GUI，只通过 API、CLI、`request.json`、`status.json` 和固定 artifacts 目录工作。

## 1. 两个入口

### 入口一：真值对照

接口：

```text
POST /api/agents/factor-lab/intake/truth-compare
```

兼容旧入口：

```text
POST /api/agents/factor-lab/agent-tasks
task_type=factor_values_compare
```

后端会统一规范为：

```json
{
  "task_type": "truth_compare",
  "skill_name": "truth_compare_v1"
}
```

目标：

```text
用户已经有一份因子值，直接和库里的标准值逐点比。
回答：这份值对不对得上、是不是重复因子、误差和覆盖率多少。
```

固定输入：

```text
factor_intake_YYYYMMDD_name/
  factor_values.csv
```

建议同时提供：

```json
{
  "factor_family": "alpha101 | wq101 | gtja191 | exploratory",
  "factor_name": "alpha1"
}
```

主要 Gate：

```text
G0 intake_validation
G1 criteria_freeze
G2 value_schema_check
G3 data_quality_check
G4 library_truth_lookup
G5 standard_truth_comparison
G6 library_similarity
G7 report_generation
G8 final_approval
```

裁决逻辑：

```text
accept ⇔
  standard_truth.status = passed
  ∧ overlap_ratio >= min_overlap_ratio
  ∧ exact_match_ratio >= pass_exact_match_ratio
  ∧ max_abs_error <= tolerance
```

如果库里没有标准真值：

```json
{
  "standard_truth": {
    "status": "not_comparable",
    "reason": "no_library_truth"
  },
  "final_decision": {
    "decision": "reject"
  }
}
```

这里的真值对照是主闸门。对不上就不能通过；没有库内真值就不能叫真值对照。

### 入口二：研报论文复现

接口：

```text
POST /api/agents/factor-lab/intake/research-reproduction
```

兼容旧入口：

```text
POST /api/agents/factor-lab/agent-tasks
task_type=research_report_reproduction
```

后端会统一规范为：

```json
{
  "task_type": "research_reproduction",
  "skill_name": "research_reproduction_v1"
}
```

目标：

```text
把研究材料转成可运行、可审核、可入库的因子。
研报不一定有标准真值，所以不能用真值作为总闸门。
```

固定输入：

```text
factor_intake_YYYYMMDD_name/
  code.py
  experiment_data.csv
  paper.pdf
  research_report.pdf
```

可选输入：

```text
truth_values.csv
truth_values.parquet
```

主要 Gate：

```text
G0 intake_validation
G1 criteria_freeze
G2 document_parse
G3 factor_spec_extraction
G4 code_reconciliation
G5 data_binding
G6 reproduction_run
G7 optional_truth_diagnostics
G8 economic_validation
G9 amr_review
G10 library_comparison
G11 report_generation
G12 final_approval
```

裁决逻辑：

```text
accept ⇔
  economic_validation.status = passed
  ∧ amr_review.status = passed
  ∧ library_comparison.status != duplicate
```

标准真值只做诊断：

```text
无真值：
  standard_truth.status = not_applicable
  不阻断

有真值且对得上：
  说明复现和参考值一致，增强可信度

有真值但对不上，同时收益有效：
  needs_review，优先怀疑实现、字段映射或口径错误

有真值且对得上，但收益无效：
  reject 或 recorded_only，说明复现正确但因子衰减
```

## 2. criteria.json 的差异

### truth_compare

```json
{
  "task_type": "truth_compare",
  "standard_truth": {
    "role": "primary_gate",
    "required": true,
    "source": "factor_library_truth",
    "missing_source_status": "not_comparable",
    "blocking": true
  },
  "decision_basis": {
    "accept_requires": [
      "standard_truth.status=passed",
      "overlap_ratio >= min_overlap_ratio",
      "exact_match_ratio >= pass_exact_match_ratio",
      "max_abs_error <= tolerance"
    ]
  }
}
```

### research_reproduction

```json
{
  "task_type": "research_reproduction",
  "standard_truth": {
    "role": "optional_diagnostic",
    "required": false,
    "source": "optional_truth_values_or_library_truth",
    "missing_source_status": "not_applicable",
    "blocking": false
  },
  "decision_basis": {
    "accept_requires": [
      "economic_validation.status=passed",
      "amr_review.status=passed",
      "library_comparison.status not in duplicate"
    ],
    "truth_diagnostics": "non_blocking_attribution"
  }
}
```

## 3. Agent 与人的分工

```text
人：
  使用 GUI 提交、查看、确认、维护规则。

Agent：
  不操作 GUI。
  读取 request.json / artifacts / Supabase 任务。
  运行复现、对照、审核、回测。
  写 status.json 和 artifacts。

后端：
  接收入口请求。
  冻结 criteria.json。
  创建 task_id。
  维护任务目录。
  后续负责写 Supabase 展示表。
```

## 4. 当前过渡状态

现在 GitHub Pages 只做展示，Agent 仍主要本地运行。两个入口的 API 已经预留：

```text
POST /api/agents/factor-lab/intake/truth-compare
POST /api/agents/factor-lab/intake/research-reproduction
GET  /api/agents/factor-lab/agent-tasks/{task_id}
```

后期网页上传时，只需要把 GUI 的提交按钮接到这两个入口；Agent 仍然通过 CLI/API/文件契约执行，不需要 GUI。
