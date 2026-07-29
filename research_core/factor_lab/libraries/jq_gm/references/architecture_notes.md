# factor_lab Proof-Batch 架构理解笔记

> Week 1 Day 2 产出 · 2026-06-22

## 一、调用链路

用户敲命令到产出报告的全路径：

```
cli.py (argparse dispatch)
  → service.py (business logic)
      → specs.py (FactorResearchSpec list)
      → factors.py (compute function)
      → validation.py (per-factor proof report)
      → reporting.py (aggregated research report)
```

## 二、cli.py — 入口层

**文件**: `research_core/factor_lab/cli.py` (219 行)

**角色**: argparse 子命令调度器。不做业务逻辑，只解析参数 + 调 service 函数。

**已有 alpha101 命令**:

| 命令 | 对应 service 函数 |
|------|------------------|
| `init-workspace` | `FactorLabWorkspaceConfig.ensure_directories()` |
| `overview` | `get_factor_lab_overview()` |
| `list-alpha101` | `list_alpha101_factors()` |
| `run-alpha101-demo` | `run_alpha101_research_job()` |
| `run-alpha101-proof-batch` | `run_alpha101_truth_proof_batch()` |
| `export-alpha101-truth-template` | `export_alpha101_truth_template()` |
| `validate-alpha101-truth` | `validate_alpha101_truth_csv()` |

**jq_gm 要加的命令**:

| 命令 | 对应 service 函数 |
|------|------------------|
| `list-jq-gm` | `list_jq_gm_factors()` |
| `export-jq-gm` | `export_jq_gm_catalog()` |
| `run-jq-gm-demo` | `run_jq_gm_research_job()` |
| `run-jq-gm-proof-batch` | `run_jq_gm_truth_proof_batch()` |

## 三、service.py — 业务逻辑层

**文件**: `research_core/factor_lab/service.py` (567 行)

**核心函数**: `run_alpha101_research_job()` (第 295 行)

**6 步执行流程**:

```
1. 生成随机数据面板
   panel = build_alpha101_demo_panel(n_dates, n_codes, seed)
   产出: DataFrame(date, code, open, high, low, close, volume, amount, vwap, returns)

2. 调用 compute 函数
   factor_frame = compute_alpha101_factors(panel, factor_names)
   产出: DataFrame(date, code, alpha1, alpha2, ...)

3. 计算评估指标
   evaluation_report = build_alpha101_evaluation_report(panel, factor_frame, factor_names)
   产出: {summary: {metrics: {alpha1: {coverage_ratio, rank_ic_mean, ...}}}}

4. 逐因子生成 proof
   for factor_name in factor_names:
       export_validation_report(spec, factor_frame, evaluation_report, ...)
       产出: runtime/factor_lab/proofs/alpha101_{factor_name}_proof.json

5. 汇总所有 proof → 综合报告
   research_report = build_alpha101_research_report(...)
   产出: runtime/factor_lab/reports/{job_id}_proof_report.{md,json}

6. 保存 job 元信息
   workspace.job_path(job_id).write_text(json.dumps(job))
   产出: runtime/factor_lab/jobs/{job_id}.json
```

**关键设计**:
- `data_source` 目前只支持 `"demo"` — 真实数据源是未来扩展点
- `truth_csv_path` 可选 — 有则做截面对比，无则跳过
- 每个因子的 proof 独立生成，互不干扰

## 四、validation.py — 校验层

**文件**: `research_core/factor_lab/validation.py` (307 行)

**核心函数**: `build_validation_report()` (第 82 行)

**五项检查**:

| # | 检查项 | 判断逻辑 |
|---|--------|---------|
| 1 | `formula_match` | `spec.formula` 非空 → passed |
| 2 | `field_mapping_match` | `spec.required_fields` ⊆ 可用列 → passed |
| 3 | `sample_point_reconciliation` | 有非空样本 → passed |
| 4 | `cross_section_truth_compare` | 有真值 CSV 且通过阈值 → passed / failed / pending_external_truth |
| 5 | `evaluation_consistency` | 有跨期截面数据 → passed |

**整体状态推断**:
```python
any failed  → "failed"
any pending → "partial"
all passed  → "passed"
```

**真值验证**: `_truth_metrics_meet_thresholds()` (第 288 行)
- 检查 `sample_point_error_ratio` 和 `cross_section_spearman`
- 与 `spec.validation_targets` 中的阈值逐项对比

## 五、specs.py — 因子声明层

**角色**: 提供 `FactorResearchSpec` 列表，是 validate + service 的数据源

**FactorResearchSpec dataclass** (18 字段):

```
factor_name         唯一标识
library             所属库
version             版本号
display_name        显示名
factor_id           外部 ID
source_document     来源文献
formula             公式表达式
description         说明
frequency           频率
sample_scope        股票池范围
required_fields     计算所需字段
parameters          参数
preprocessing       预处理步骤
neutralization      中性化方法
validation_targets  验证阈值 (4 项)
tags                分类标签
notes               备注
metadata            扩展信息 (gm_field, gm_fields 等)
```

## 六、关键扩展点

jq_gm 因子库要接入这条管线，需要修改/新增的位置:

1. **`cli.py`**: 加 4 个子命令 (复用已有 argparse 模式)
2. **`service.py`**: 新增 `run_jq_gm_research_job()` (复用 `run_factor_set_research_job()` 的骨架)
3. **`specs.py`**: 提供 215 个 `FactorResearchSpec` ✅ 已完成
4. **`factors.py`**: 提供 `compute_jq_gm_factors(panel, factor_names) → DataFrame` ✅ 已完成
5. **`validation.py`**: 不动 — 它是通用的，只依赖 Spec 格式
6. **`reporting.py`**: 不动 — 同上

## 七、与 CrossvalidationTYD 的对应关系

```
AgentMatrix 管线              CrossvalidationTYD 对应
─────────────────────────     ───────────────────────
cli.py 子命令                 pipeline.py CLI
service.py research_job       pipeline.py run()
specs.py FactorResearchSpec   FACTOR_REGISTRY (但格式不同)
factors.py compute             gm_factor_lib.calc_factors()
validation.py proof           auto_diagnostic.py (不同层次)
reporting.py 综合报告          auto_report.py
```
