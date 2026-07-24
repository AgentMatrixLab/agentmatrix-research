# Factor Lab Architecture V2

本文档定义 Factor Lab 从输入、复现、判定、入库、策略生成、监控降级到展示分发的 V2 架构。V2 的核心变化是：流程顶端不再是人工审批，而是判据冻结。人不再默认给单个因子盖章，而是在例外情况下维护规则。

## 核心原则

1. 判据先于执行存在。
2. 执行者只能读取判据，不能修改判据。
3. Hermes 是生产者，只产出事实。
4. AMR 是审核者，只审核事实，不能改 Hermes 原始产物。
5. 裁决不等于入库，入库不等于分发。
6. GitHub Pages 只做只读展示，不执行动态流程。
7. 人的常规产出是规则，不是单个因子的放行意见。
8. 任何缺省、缺失、未注册的情况一律 fail-safe，不得 fail-open。

## 第 1 层：判据层

回答的问题：什么叫通过。

旧架构把“人类决策层”放在最顶端。V2 把顶层改成判据层。原因是 Alpha101 被错标成 `not_applicable` 的根因不是没人审批，而是“是否需要真值对照”这件事曾经由执行方自己决定。人看到的是一个自洽界面，很难发现底层判据被执行方改过。

### factor registry

因子判据的唯一规则源，按因子族维护：

| factor_family | truth_required | tolerance | min_overlap_ratio | pass_exact_match_ratio | promotion_policy |
| --- | --- | --- | --- | --- | --- |
| `alpha101` / `wq101` | true | `1e-8` | `0.90` | `0.99` | `auto` |
| `gtja191` | true | `1e-8` | `0.90` | `0.99` | `human_confirm` |
| `exploratory` | false | — | — | — | `auto` |

未注册因子族必须 fail-safe：

```json
{
  "criteria_status": "failed",
  "criteria_error": "unknown_factor_family",
  "truth_required": true
}
```

人在这一层维护规则，写一次管一族。人的常规工作量是 `O(规则数)`，不是 `O(因子数)`。

### strategy_policy registry

策略判据的唯一规则源，与因子判据分开维护：

| strategy_family | strategy_gate_required | min_sharpe | max_drawdown | max_turnover | max_industry_exposure | approval_policy |
| --- | --- | --- | --- | --- | --- | --- |
| `ic_weighted_long_short` | true | `1.0` | `0.20` | `0.60` | `0.30` | `auto` |
| `market_neutral_multi_factor` | true | `1.2` | `0.15` | `0.50` | `0.15` | `human_confirm` |
| `exploratory_strategy` | false | — | — | — | — | `human_confirm` |

未注册策略族必须 fail-safe：输出 `unknown_strategy_family`，阻断自动分发，进入人工队列。

### decay_policy

监控与降级的判据源，写在因子族 registry 中。监控 Agent 只能计算滚动指标并与之比对，不能自己定义“效果下降”：

| factor_family | min_rolling_ic | review_window | max_similarity_drift | max_coverage_gap | decay_action |
| --- | --- | --- | --- | --- | --- |
| `alpha101` / `wq101` | `0.02` | `250d` | `0.20` | `0.10` | `needs_review` |
| `gtja191` | `0.02` | `250d` | `0.20` | `0.10` | `needs_review` |
| `exploratory` | `0.01` | `120d` | `0.30` | `0.20` | `auto_deprecate` |

`decay_action` 取值：

| 取值 | 行为 |
| --- | --- |
| `needs_review` | 进入人工队列，由人决定是否 `deprecated` |
| `auto_deprecate` | 直接标记 `deprecated`，不惊动人 |

### G0 判据冻结

G0 做三件事：

1. 查 registry 得出本次任务判据。
2. 写入 `criteria.json`。
3. 计算 `criteria_sha256` 并写入 `request.json` 和 `status.json`。

任务提交里的覆盖字段不能修改判据。即使 intake 里写了 `truth_required=false`，只要 registry 对该因子族规定为 true，最终冻结结果仍然是 true。

`criteria.json` 冻结后向下游只读传递。每个 Gate 入口先重算 hash 并与 `status.json.criteria_sha256` 比对，不一致直接返回：

```text
criteria_tampered
```

校验必须放在统一 Gate 入口，例如 `_enter_intake_gate()`，不能依赖各 Gate 自觉调用。

当前 hash 机制用于检测意外篡改，例如 Agent 覆盖错文件或 patch 重跑带错文件。它不是对抗性安全边界。如果要防有意绕过，`criteria_sha256` 必须存放在 Agent 无写权限的数据库表、只读日志或只读 API 中。

策略任务与监控任务各有自己的判据冻结（S0 / M0），机制与 G0 相同，判据文件与 hash 字段独立。

## 第 2 层：生产层

回答的问题：算出来是什么。

输入契约包含三类任务：

1. 研报复现：`code.py`、`experiment_data.csv`、`paper.pdf`、`research_report.pdf`。
2. 因子值对照：`factor_values.csv`。
3. 真值对照：`factor_values.csv`、`truth_values.csv`。

研报复现任务可以可选携带 `truth_values.csv`。

### G1 Hermes 复现

Hermes 是纯生产者，负责：

- 解析 PDF。
- 抽取公式。
- 判断代码与文档是否一致。
- 缺字段时调用 Quant API 补数据。
- 生成 `factor.py`。
- 生成 `test_factor.py`。
- 跑出 `factor_values.parquet`。
- 计算 IC、RankIC、IR、覆盖率、换手率。

Hermes 的所有产物放在：

```text
hermes_out/
  parsed_paper.md
  parsed_research_report.md
  extracted_formula_raw.json
  factor.py
  test_factor.py
  factor_values.parquet
  reproduction_log.json
  hermes_report.md
```

`hermes_out/` 只能由 Hermes 写。AMR 不能写这个目录。责任边界由目录结构保证，不靠自觉。

Hermes 只产出事实，不评价事实。它可以算出 `IC=0.05`，但 `0.05` 算不算好不归 Hermes 判断。

## 第 3 层：判定层

回答的问题：算出来的东西合不合格。

### G2 真值对照

真值对照是 V2 里最关键的一层。它逐点比对复现值和外部权威真值，输出：

- `exact_match_ratio`
- `max_abs_error`
- `mean_abs_error`
- `rmse`
- `overlap_ratio`
- `mismatch_count`

判定规则：

```text
passed ⇔ overlap_ratio >= min_overlap_ratio
       ∧ exact_match_ratio >= pass_exact_match_ratio
       ∧ max_abs_error <= tolerance
```

三个阈值全部来自 `criteria.json`。

覆盖率不足不能算 passed。比如 20 只股票对 5465 只真值，即使 20 只完全匹配，也必须是 `not_compared`。比不了就是没比，不是通过。`failed` 只表示已经在足够覆盖率上完成对照但数值不匹配。

状态枚举必须区分：

| 状态 | 含义 |
| --- | --- |
| `passed` | 真值对照通过 |
| `failed` | 覆盖率满足要求，但匹配率或误差没有通过 |
| `not_applicable` | registry 判定 `truth_required=false` |
| `not_compared` | 该比但没接真值、真值缺失或覆盖不足 |

`not_applicable` 只能由 `truth_required=false` 推出，永远不能由“没找到文件”推出。

### G3 AMR 审核

AMR 是审核者，负责：

- 审核代码可读性。
- 审核数据字段映射。
- 审核假设是否合理。
- 审核评价结果是否有效。
- 记录风险点。

AMR 如果认为 Hermes 错了，输出：

```text
amr_out/
  code_review.json
  evaluation_review.json
  suggested_patch.diff
  amr_report.md
  final_decision.json
```

AMR 不能原地覆盖 `hermes_out/factor.py`。`suggested_patch.diff` 只能由人决定是否采纳。采纳后作为新 attempt 回到 G1，并记录：

```json
{
  "parent_task_id": "task_id",
  "patch_source": "amr"
}
```

AMR 认为判据本身不合理时，只能输出 `needs_review`，不能自行调整 `tolerance` 或 `truth_required`。

### G4 因子库对照

G4 做查重与复用判断：

- 与已有因子的 Pearson 相关性。
- Spearman 相关性。
- overlap ratio。
- 是否只是已有因子的线性变换。
- 是否建议复用已有因子。

## 第 4 层：裁决与入库

回答的问题：该怎么处置。

### G5 自动裁决

G5 汇总 G2、G3、G4 的结果做分流：

| 条件 | 结果 |
| --- | --- |
| `passed` 或 `not_applicable`，且无冲突 | 候选通过 |
| `failed` / `not_compared` | 驳回，不惊动人 |
| `needs_review` / `criteria_tampered` / `unknown_factor_family` | 进入人工队列 |

裁决不等于入库。G5 只形成结论，执行归 G6。

### G6 promotion

G6 根据 registry 里的 `promotion_policy` 执行：

| promotion_policy | 行为 |
| --- | --- |
| `auto` | 自动 promotion |
| `human_confirm` | 进入确认队列 |

哪些因子族需要人确认是一条可查的规则，不是临场判断。如果公司要求全部人工确认，把 registry 默认值改成 `human_confirm`，架构不需要变。

Registry 状态机：

```text
draft -> candidate -> registered -> production
```

辅助状态：

```text
deprecated      由 M2 降级裁决写入
needs_review    由 G5 / S2 / M2 写入
```

## 第 5 层：策略任务

回答的问题：这批因子能组成什么策略，策略是否达标。

### 策略任务边界

策略任务是独立任务，不是因子任务 G6 之后继续沿用同一个 `task_id`。一个策略通常组合多个已入库因子，因此它有自己的任务 ID、自己的判据冻结和自己的状态文件。

因子任务结束于：

```text
G0 -> G1 -> G2 -> G3 -> G4 -> G5 -> G6 -> 正式因子库
```

策略任务从正式因子库读取输入：

```text
正式因子库 -> S0 -> S1 -> S2 -> 分发
```

### S0 策略判据冻结

S0 从 `strategy_policy registry` 解析策略族判据，写入：

```text
strategy_criteria.json
strategy_criteria_sha256
```

S0 与 G0 的原则相同：判据来自 registry，不能由策略 Agent 临场定义。每个策略 Gate 入口都要校验 `strategy_criteria_sha256`。

### S1 策略生成与回测

S1 负责把正式因子组合成策略，并运行回测。它回答的问题是：基于已通过的因子，能生成什么策略事实。

策略生成 Agent 可以做：

- 选择因子组合。
- 设置权重方式。
- 设置股票池。
- 设置调仓频率。
- 生成策略配置。
- 运行回测。
- 输出收益、回撤、夏普、换手、行业暴露、持仓、归因。

但 S1 仍然只生产事实，不决定策略是否合格。策略产物落到：

```text
strategy_out/
  strategy_config.json
  backtest_result.parquet
  performance.json
  risk_exposure.json
  holdings_sample.parquet
  strategy_report.md
```

### S2 策略自动裁决

S2 负责判断策略是否达标。它回答的问题是：策略结果是否满足被冻结的策略判据。

S2 不能临场决定夏普下限、回撤上限、换手上限或行业暴露约束。判定规则（左侧为回测指标，右侧为 `strategy_criteria.json` 里的阈值）：

```text
strategy_passed ⇔ sharpe             >= min_sharpe
                ∧ drawdown           <= max_drawdown
                ∧ turnover           <= max_turnover
                ∧ industry_exposure  <= max_industry_exposure
```

`strategy_gate_required=false` 时，S2 必须输出 `decision=not_applicable`，并由 `approval_policy=human_confirm` 进入人工确认。`not_applicable` 表示按 registry 规则不需要自动裁决，是正常态；`needs_review` 只用于未知策略族、判据缺失、结果冲突或执行异常。阈值缺失不能 fail-open。

S2 输出 `strategy_decision.json`：

- `decision`: `accept` / `reject` / `needs_review` / `not_applicable`
- `approval_policy`: `auto` / `human_confirm`
- `criteria_source`
- `strategy_criteria_sha256`
- `blocking_errors`
- `risk_notes`

S2 裁决不等于分发。进入信号包、实盘候选或对外展示仍然要看 `approval_policy` 和权限规则。

## 第 6 层：监控与降级

回答的问题：已经入库的因子是否还应该保持当前状态。

监控与降级不是人工临场判断，也不是监控 Agent 自己定线。它使用 registry 中的 `decay_policy`。

### M0 监控判据冻结

M0 从 registry 读取 `decay_policy`，冻结到：

```text
monitor_criteria.json
monitor_criteria_sha256
```

监控任务和因子任务、策略任务一样，必须在统一入口校验 hash。

### M1 滚动监控

M1 只负责计算事实，每一项都对应 `decay_policy` 里的一个阈值：

| 指标 | 对应阈值 |
| --- | --- |
| `rolling_ic` | `min_rolling_ic` |
| `similarity_drift` | `max_similarity_drift` |
| `coverage_gap` | `max_coverage_gap` |

统计窗口由 `review_window` 决定。M1 不做任何判断。

### M2 降级裁决

M2 只负责把 M1 的指标和 `monitor_criteria.json` 比对：

```text
decay_triggered ⇔ rolling_ic       <  min_rolling_ic
                ∨ similarity_drift >  max_similarity_drift
                ∨ coverage_gap     >  max_coverage_gap
```

触发后按 `decay_action` 执行：

| decay_action | 行为 |
| --- | --- |
| `needs_review` | 因子状态置 `needs_review`，进入人工队列，由人决定是否 `deprecated` |
| `auto_deprecate` | 因子状态直接置 `deprecated` |

`deprecated` 只能由 M2 写入。没有任何 Agent 或人可以绕过 `decay_policy` 直接标记降级。

## 第 7 层：数据与产物

回答的问题：数据从哪来，存哪去。

数据链路：

```text
原始数据湖 -> 标准化数据层 -> Serving DB
```

原始数据湖保存全量日线、分钟、Tick、财务、行业、复权、指数等原始数据。

标准化数据层使用 parquet 大表，按日期、股票、因子族等分区。

Serving DB 保存面板要读的结构化信息。

### 权限分层

GitHub Pages 只能读公开只读表：

```text
public_dashboard_tasks
public_dashboard_metrics
public_dashboard_reports
```

后端 service role 才能访问私有表：

```text
tasks
task_files
factor_values
final_decisions
promotion_logs
```

Storage bucket 也要分层：

```text
public-reports
private-inputs
private-artifacts
```

PDF、parquet、源码、完整评估文件默认私有。公开层只展示脱敏摘要、指标和报告链接。

## 第 8 层：展示与分发

回答的问题：结果给谁看。

GitHub Pages 面板只读 Supabase 公开表。GitHub Pages 是静态站，anon key 一定暴露在浏览器里，所以必须开启 RLS，并且 anon key 只能 `SELECT` 公开表。

分发链路：

```text
S2 accept + approval_policy 通过
  -> 信号打包（日期、策略版本、标的、权重）
  -> 模拟盘 / 客户端对接（权限控制、按时抓取）
```

所有写操作都走后端：

- 上传文件
- 写任务状态
- 写 Agent 产物
- promotion
- 回填
- 状态变更

展示层不跑任何流程，只负责渲染。

## 例外层：人

人不在主干流程顶端，而是在旁边处理例外。人只在以下情况下出现：

| # | 触发条件 | 人做什么 |
| --- | --- | --- |
| 1 | 规则缺口：`unknown_factor_family`、AMR 结论与硬检查矛盾 | 补 registry 规则 |
| 2 | 抽样审计 | 复核样本，必要时熔断 |
| 3 | `promotion_policy=human_confirm` | 确认因子入库 |
| 4 | `approval_policy=human_confirm`（含 `exploratory_strategy`） | 确认策略分发 |
| 5 | `unknown_strategy_family` | 补 strategy_policy 规则 |
| 6 | `decay_action=needs_review` | 决定是否 `deprecated` |
| 7 | AMR 提出 `suggested_patch.diff` | 决定是否采纳（归入第 1 类队列） |

采纳 patch 必须作为新 attempt 回到 G1，并记录 `parent_task_id` 和 `patch_source=amr`。

### 抽样审计与熔断

抽样审计异步执行，不阻塞主流程。

- 发现单点问题：标记对应因子或策略为 `needs_review`。
- 发现系统性错误（同一批次、同一因子族或同一 Agent 产物重复出错）：触发熔断——暂停该范围内的 promotion 与分发，批量回退到 `needs_review`，要求补 registry 规则或修复执行链后重跑。

熔断范围内的后续 promotion 必须暂停，直到熔断解除。

### 人的产出

人的产出永远是规则，不是单个因子的放行。人补规则并写回 registry 后，被卡住的任务重跑 G0，下次同类任务不再需要人。

## 存量回填

新判据只作用于新任务。历史任务和历史展示数据不会自动变正确。

上线前必须做一次存量回填：按新 registry 规则重判所有历史任务与展示数据。凡是 registry 判定 `truth_required=true`、但历史状态为 `not_applicable` 且没有真值对照证据的因子，一律改判为 `not_compared`。

回填脚本默认 dry-run：

```text
python scripts/backfill_truth_status.py
```

确认影响范围后再执行：

```text
python scripts/backfill_truth_status.py --apply
```

回填范围必须覆盖前端实际读取的所有路径，包括 `runtime/factor_lab`、`frontend/factor-lab-dashboard/data`、`pages/factor-lab-dashboard/data`。

执行 `--apply` 前需要团队周知，因为界面上会出现一批状态从“无需对照”变成“未对照”。这不是回归，而是暴露真实状态。

## 主流程摘要

```text
factor registry
  -> G0 判据冻结
  -> G1 Hermes 复现
  -> G2 真值对照
  -> G3 AMR 审核
  -> G4 因子库对照
  -> G5 自动裁决
  -> G6 promotion
  -> 正式因子库

正式因子库
  -> S0 策略判据冻结
  -> S1 策略生成与回测
  -> S2 策略自动裁决
  -> 信号打包 / 模拟盘对接
  -> GitHub Pages 只读展示

正式因子库 / 正式策略库
  -> M0 监控判据冻结
  -> M1 滚动监控
  -> M2 降级裁决
  -> needs_review / deprecated
```

三条链共用同一套机制：判据来自 registry，在链首冻结并计算 hash，每个 Gate 入口校验，执行者只读。

## 附录：画图约定

分层、每层一个职责、左侧标层名。第一层是“判据层”，不是“人类决策层”。

配色：

- 紫色：判据与规则
- 绿色：自动执行与裁决
- 橙色：人和例外路径
- 灰色：端点与基础设施

人画在主干旁边，不画在主干顶部。虚线连接表示例外介入。
