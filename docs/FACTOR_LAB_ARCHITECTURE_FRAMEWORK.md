# Factor Lab 架构总控框架 v0.1

本文档用于把 Factor Lab 的长期蓝图收敛成当前仓库可落地的架构边界。它不是一次性功能清单，而是后续前端、后端、Agent、因子复现、策略回测协作时共同遵守的框架。

## 1. 总原则

Factor Lab 的目标不是先做一个很复杂的页面，而是逐步形成一个可信的因子研究工作台。所有能力都围绕三件事展开：

1. 让人提出研究意图。
2. 让 Agent 或后端流程自动执行。
3. 让系统用可追溯的产物证明结果是否可信。

因此系统必须遵守以下边界：

- 前端只展示真实产物，不编造指标、结论或推荐。
- 只读适配层只读取已有结果，不写核心数据，不触发因子计算、truth 对比、proof 判定或回测。
- 执行侧可以写 runtime 产物，但必须把结果落成结构化 JSON，供前端和云端读取。
- 所有状态变化必须来自可追溯产物或 gate event，不能只靠页面状态。
- Agent 产出的因子先进入待验证/待审核区，不能直接进入正式因子库。

## 2. 当前仓库的现实分层

### L0: 因子展示与只读视图层

当前已有：

- `frontend/factor-lab-dashboard/`: Factor Lab 前端页面。
- `backend/factor_lab_api.py`: 本地 Flask API，负责把只读适配层暴露给前端。
- `research_core/factor_lab_web/`: 只读 view model 适配层，负责把 specs、runtime reports、artifacts 整理成前端稳定读取格式。
- `docs/FACTOR_LAB_FRONTEND_CONTRACT.md`: 当前前端契约。

职责：

- 展示因子库、复现状态、truth/proof 状态、单因子详情、报告产物。
- 读取 `libraries/*/specs.py` 和 runtime 中已经生成的报告。
- 不做因子计算，不跑 Agent，不抓行情，不写核心结果。

当前判断：

- 这是目前最应该稳定的部分。
- 它是公司内部协作的入口，也是后续云端同步、人工审核、Agent 接入的展示基础。

### L1: 因子复现与验证执行层

当前已有：

- `research_core/factor_lab/service.py`
- `research_core/factor_lab/runtime.py`
- `research_core/factor_lab/validation.py`
- `research_core/factor_lab/truth.py`
- `research_core/factor_lab/evaluation.py`
- `research_core/factor_lab/reporting.py`
- `research_core/factor_lab/inference.py`
- `research_core/factor_lab/similarity.py`
- `research_core/factor_lab/factor_validate.py`
- `research_core/factor_lab/e2e_validation.py`

职责：

- 运行因子复现。
- 生成 proof、truth_compare、evaluation、report、factor_frame 等产物。
- 做 IC/IR、bootstrap、OOS、相似度等研究验证。

当前判断：

- 这层已有不少能力，但还没有统一成完整生命周期。
- 不应该再新造一套验证逻辑；未来如果要做 step-level harness，也应该复用这些模块，而不是重写。
- 目前前端应读取这层已经生成的产物，而不是直接调用这层执行逻辑。

### L2: 策略研究与回测层

当前已有：

- `research_core/qlib_lab/`
- `research_core/backtest_adapter/`
- `research_core/strategy_engine/`
- `scripts/*_agent_engine.py`

职责：

- 因子组合。
- 策略构建。
- 回测适配。
- 成本、滑点、换手、持仓、基准对比。

当前判断：

- 这层目前可以作为后续能力储备，但不应现在强行塞进 Factor Lab 前端主流程。
- 在真实数据 API、PIT 数据、股票池、手续费滑点、调仓规则没有统一前，不应把策略收益曲线当作可靠结论展示。
- 前端可以预留策略页或禁用按钮，但不要展示假的策略收益。

### L3: Agent 自动化层

当前已有迹象：

- `research_core/qlib_lab/auto_factor_miner.py`
- 多个 `scripts/*_engine.py`
- 外部 Trae / Claude Code / Codex / Hermes Agent 使用场景。

目标职责：

- 从论文、想法、已有因子组合中自动生成候选因子。
- 自动复现、验证、筛选。
- 通过 gate 后进入人工审核。
- 审核后进入云端因子库。

当前判断：

- 这层是未来方向，但现在不要把它做成假自动化。
- 当前最合理的是在前端保留“AI Agent 接入”入口，说明能力预留，不实际驱动 Agent。

## 3. 两套契约的关系

### 当前契约: `factor_lab_view_v1`

这是现在前端应该消费的契约。

用途：

- 因子库展示。
- 单因子详情。
- 报告中心。
- artifact 列表。
- truth/proof/evaluation 状态展示。

特点：

- 从当前 repo 真实产物整理而来。
- 低侵入。
- 服务当前前端。

### 目标契约: `factor_lifecycle_v1`

这是未来全自动化平台应演进到的生命周期契约。

建议实体：

- `factor_spec`: 因子定义。
- `data_snapshot`: 数据快照。
- `replication_run`: 复现运行。
- `evaluation_report`: 评估报告。
- `strategy_spec`: 策略定义。
- `backtest_run`: 回测运行。
- `gate_event`: 状态流转事件。
- `deployment_record`: 上线或入库记录。

当前决策：

- 不要立刻替换 `factor_lab_view_v1`。
- 先保留现有前端契约。
- 后续新增一层 mapping，把已有 runtime 产物逐步映射到 `factor_lifecycle_v1`。

## 4. Gate 设计

未来所有因子都应该通过 gate 流转，而不是页面手动改状态。

建议 gate 阶段：

- G0: 因子定义检查，包括字段、公式、依赖、重复度。
- G1: 复现检查，包括 proof 是否成功、产物是否完整。
- G2: 研究评估，包括 IC/IR、coverage、bootstrap、OOS、相似度、trial 记录和多重检验依据。
- G3: 策略评估，包括换手、成本、滑点、基准对比、回撤。
- G4: 人工审核，包括是否入库、是否进入策略研究、是否退回重跑。

当前决策：

- 现在不要急着实现完整 gate 引擎。
- 可以先在文档和数据契约里定义 gate event。
- 等真实数据、truth 和策略层稳定后再落地。
- G4 编号明确采用“人工审核”，因为它贴合当前前端和公司工作流。
- 前向验证不再占用 G4 编号，但不能从目标架构中删除。未来应挂在 `deployment_record` 上，作为策略进入生产或持续观察前的前置验证。

### Trial Ledger

trial 记录不能推迟到完整 gate 引擎之后。

原因：

- 多重检验和 FDR 校正依赖候选因子的真实尝试次数。
- 过去没有记录的 trial，将来无法可靠补回。
- 如果只记录通过的因子，系统会天然低估搜索次数，导致后续统计校正偏乐观。

当前最小要求：

- 在执行侧新增 append-only trial ledger。
- 每生成一个候选因子，无论是否提交、是否通过，都追加一条记录。
- 最小字段包括 `timestamp`、`search_family`、`spec_hash`、`source_engine`。
- 初版可以是 JSONL 文件，不要求立刻进入数据库。
- 这属于执行侧记录，不属于 `factor_lab_web` 只读适配层。

## 5. 前端页面的职责边界

### 因子库

现在应该保留并继续打磨。

职责：

- 展示所有已声明因子。
- 展示所属库、分类、复现状态、truth 状态、IC/IR、覆盖率、最近校验时间。
- 支持搜索、筛选、排序。
- 点击已复现或待审核因子进入单因子详情。

不做：

- 不直接运行因子。
- 不直接修改因子定义。
- 不展示没有真实来源的收益曲线。

### 单因子详情

现在可以继续保留。

职责：

- 展示复现状态、truth/proof 结果、artifact。
- 预留单因子分层研究和 IC 时序区域。
- 明确提示当前是否为真实研究数据。

不做：

- 不把分层研究等同于可交易策略收益。
- 不在数据未接入时伪造图表。

### 报告中心

建议保留，但需要权限控制。

职责：

- 展示 job 报告、runtime 产物、失败原因、路径、内部验证细节。

原因：

- 这里会包含公司内部数据、路径、系统流程和失败细节。
- 适合员工访问，不适合游客公开访问。

### 人工审核

建议保留为未来页面。

职责：

- 审核 Agent 或同事提交的复现结果。
- 决定是否入库、退回、重跑、标记风险。

当前状态：

- 可以先做页面占位。
- 不急着接真实审核工作流。

### AI Agent 接入

建议保留为路线图页面。

职责：

- 说明未来可接 Trae、Claude Code、Codex、Hermes Agent 或公司内部 Agent。
- 定义 Agent 输出必须遵守的提交格式。

当前状态：

- 只展示预留能力。
- 不实际驱动 Agent。

### 因子监控 / 策略监控

保留式降级，不作为当前核心建设。

原因：

- 因子监控需要真实数据、IC 时序、OOS、稳定股票池。
- 策略监控需要策略定义、交易成本、调仓规则、持仓和基准。
- 现在做容易变成漂亮但不可信的空壳。

处理方式：

- 页面可以保留，避免把已有设计直接砍掉。
- 数据只读已有产物，不伪造实时监控或收益结论。
- 页面顶部必须保留数据信任横幅，例如：“当前数据未经 PIT / 幸存者偏差 / 成本模型治理，仅供研究参考。”
- 等 M3 数据治理完成后，再移除或降级该提示。

## 6. 数据层优先级

在做策略收益、资产排名、监控面板前，必须先解决数据可信问题。

优先级：

1. 数据来源统一。
2. 时间点正确，避免未来函数和前视偏差。
3. 股票池明确，处理退市、停牌、ST、新股。
4. 成本模型明确，包括手续费、印花税、滑点。
5. 数据快照可追溯。

没有这些，前端不应展示“赚钱能力”类结论。

## 7. 短期路线图

### M1: 稳定当前前端和只读适配层

目标：

- 因子库稳定读取 specs。
- 单因子详情稳定读取 artifacts。
- 报告中心稳定读取 job reports。
- 所有字段来自真实产物。

不做：

- 不做策略收益。
- 不做真 Agent 自动化。
- 不做伪实时监控。

### M1.5: 新增 Trial Ledger

目标：

- 记录所有候选因子尝试，而不是只记录成功因子。
- 为未来 FDR、多重检验、deflated Sharpe、搜索偏差校正提供事实基础。
- 初版使用 append-only JSONL 即可。

最小字段：

- `timestamp`
- `search_family`
- `spec_hash`
- `source_engine`

边界：

- 这是执行侧日志，不进入只读适配层的写路径。
- 不要求现在做 FDR 判定。
- 不要求现在接入 gate 引擎。

### M2: 定义生命周期数据模型

目标：

- 新增 `factor_lifecycle_v1` 文档。
- 明确 factor、run、evaluation、gate、artifact 的关系。
- 让后续 Agent、云端库、人工审核都按同一套结构提交。
- 必须包含现有 runtime 产物到 lifecycle 实体的字段映射表，标注“直接映射 / 需转换 / 缺失”。
- 必须包含 `gate_event` schema。
- 必须包含 `trial_ledger` schema。
- 必须明确 G4 为人工审核。
- 必须在 `deployment_record` 中预留前向验证字段。

### M3: 接入真实研究数据

目标：

- 支持时间区间。
- 支持股票池。
- 支持 IC/IR 时序。
- 支持分层收益研究。
- 支持 OOS 和 bootstrap 结果。

### M4: 接入人工审核

目标：

- 已复现/待审核/已入库/退回重跑状态清晰。
- 审核动作产生 gate event。
- 审核记录可追溯。

### M5: 策略层接入

目标：

- 多因子组合。
- 成本和滑点。
- 基准对比。
- 回撤、换手、持仓、收益曲线。

前提：

- 数据层和研究层已经可信。

### M6: Agent 自动化

目标：

- Agent 接收研究意图。
- 自动生成候选因子。
- 自动复现和评估。
- 结果进入审核队列。

前提：

- gate、artifact、审核、云端库都已经规范化。

## 8. 当前明确不做

以下内容当前不应该作为重点：

- 为了好看伪造资产排名或策略监控数据。
- 在没有真实数据 API 时展示可交易策略收益。
- 为每次前端小改动都重新打桌面包。
- 新建一套重复 `inference.py`、`factor_validate.py`、`similarity.py` 的验证逻辑。
- 把执行侧有副作用的模块塞进 `factor_lab_web` 只读适配层。

## 9. 下一步执行建议

当前最合理的推进顺序：

1. 收口当前 PR，确保 `factor_lab_web` 只读适配层合并。
2. 加 trial ledger，先把候选因子的搜索尝试记录下来。
3. 稳定前端因子库和单因子详情，不再频繁改大结构。
4. 单独写 `factor_lifecycle_v1` 契约草案，作为下一轮后端/Agent 对齐材料。
5. 等真实数据和 truth 接入后，再做单因子研究图表。
6. 等研究图表可信后，再做策略层。

一句话总结：

Factor Lab 现在不要急着变成全自动 Alpha 工厂。当前阶段最重要的是先成为一个“可信、只读、可追溯的因子研究展示与协作入口”。等数据、验证、gate、审核稳定后，再逐层接入策略和 Agent 自动化。
