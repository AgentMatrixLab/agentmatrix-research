# Factor Lab 数据入口 README

数据入口分两类，但每一类都只给 Agent 一份总 Skill。Agent 按对应 Skill 把输入整理成系统可读取的任务目录、状态文件和 artifacts。

## 页面行为

页面有两个按钮：

```text
研报自动复现
因子值对照
```

点击不同按钮时，页面展示对应的 Agent Skill。用户选择文件后，每个文件都可以点“查看”预览。

## 研报自动复现总 Skill

```text
Agent Skill: research_report_reproduction_v1
```

### 目标

读取一个研报复现包，复现因子，生成因子值、评估结果、因子库对照和最终决策。

### 输入包

四个文件合在一起看作一个整体研究包：

```text
factor_intake_YYYYMMDD_name/
  code.py
  experiment_data.csv
  paper.pdf
  research_report.pdf
```

Agent 不要把四个文件当成四个独立任务。它们共同描述同一个研究问题：

- `code.py`：参考实现或无代码占位。
- `experiment_data.csv`：实验数据或样例数据。
- `paper.pdf`：理论来源、变量、公式、实验口径。
- `research_report.pdf`：最终因子定义、组合假设、图表口径、结论。

### 标准输出

```text
runtime/factor_lab/agent_tasks/<task_id>/
  request.json
  status.json
  artifacts/
    normalized_report.md
    extracted_formula.json
    assumptions.json
    factor.py
    test_factor.py
    factor_values.parquet
    evaluation.json
    library_comparison.json
    reproduction_report.md
    final_decision.json
```

## 因子值对照总 Skill

```text
Agent Skill: factor_values_compare_v1
```

### 目标

读取外部因子值，与当前因子库做相似度、重复性、IC/IR、复用建议和入库建议对照。

### 输入包

```text
factor_intake_YYYYMMDD_name/
  factor_values.csv
```

`factor_values.csv` 必需列：

```csv
date,symbol,factor_value
2024-01-02,000001.SZ,0.1234
2024-01-02,000002.SZ,-0.0345
```

可选列：

```text
factor_name
source_weight
is_valid
```

### 标准输出

```text
runtime/factor_lab/agent_tasks/<task_id>/
  request.json
  status.json
  artifacts/
    input_profile.json
    data_quality.json
    library_similarity.json
    evaluation.json
    comparison_report.md
    final_decision.json
```

## 共同规则

- 中间过程不问人。
- 不确定信息写入 `assumptions.json`、`input_profile.json` 或 `data_quality.json`。
- Agent 不能直接写正式因子库。
- 新候选先进入 `quarantine`。
- 最终人工只确认 `final_decision.json`。
