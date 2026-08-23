# Factor Lab Agent 框架优化方案

本文档总结成熟 Agent 框架的设计优点，并把它们映射到 Factor Lab 当前系统中。目标不是把 LangGraph、AutoGen、CrewAI、OpenAI Agents SDK、MCP 全部硬塞进项目，而是吸收它们经过验证的结构，让 Agent 更愿意走 Factor Lab 的标准路径，同时让绕过标准路径的结果无法直接入库。

## 1. 核心问题

老师提出的问题是：

```text
Agent 可能不按我们的框架走。
它可能自己从网络上找资料、写脚本、拉数据、生成一套结果，然后绕开平台提交。
```

所以系统不能只靠 README 或口头约束。必须同时满足两点：

```text
1. 正确路径比乱跑更短、更清楚、更容易成功。
2. 乱跑出来的结果即使存在，也不能直接进入正式因子库或展示层。
```

## 2. 成熟框架可借鉴点

### 2.1 LangGraph：状态图、checkpoint、可恢复执行

可借鉴点：

```text
1. 每个任务是一个显式状态图，而不是一段自由发挥的对话。
2. 每个节点完成后写 checkpoint。
3. 支持失败恢复、人工介入、回到历史状态重新执行。
4. 长流程不依赖模型上下文记忆，而依赖持久化状态。
```

映射到 Factor Lab：

```text
task_id/
  request.json
  status.json
  artifacts/
  gate_events.jsonl
  checkpoints/
    G0_criteria_freeze.json
    G1_validate_package.json
    G2_submit_payload.json
```

新增模块：

```text
Agent Task Graph
Gate Checkpoint Store
Gate Event Log
Resume / Retry API
```

### 2.2 OpenAI Agents SDK：guardrails、tool guardrails、tracing、handoff

可借鉴点：

```text
1. 输入 guardrail：Agent 开始前先检查输入。
2. 输出 guardrail：Agent 产出后再检查格式和安全性。
3. tool guardrail：每次工具调用前后都检查。
4. tracing：记录 Agent 调了什么工具、输入输出是什么。
5. handoff：任务可以从一个 Agent 转交给另一个 Agent。
```

映射到 Factor Lab：

```text
输入 guardrail:
  检查 manifest.json、文件结构、schema、source_hash。

输出 guardrail:
  检查 final_report.json、truth_comparison.json、library_comparison.json 是否符合 schema。

tool guardrail:
  Agent 调 Quant API、网络抓取、Supabase 写入前必须记录来源和权限。

handoff:
  上传 Agent -> 论文复现 Agent -> AMR 审核 Agent -> promotion Agent。
```

新增模块：

```text
contracts/*.schema.json
guardrails/input_guardrails.py
guardrails/output_guardrails.py
guardrails/tool_guardrails.py
traces/agent_tool_calls.jsonl
handoff_manifest.json
```

### 2.3 CrewAI：Crew、Task、Flow、工具、观测、人机触发

可借鉴点：

```text
1. 把 Agent 角色分清楚。
2. 把任务拆成明确 Task。
3. 用 Flow 编排长流程。
4. 每个 Agent 只拿到自己需要的工具。
5. 生产系统必须有 observability。
```

映射到 Factor Lab：

```text
Upload Agent:
  只负责 init / validate / submit。

Reproduction Agent:
  只负责复现代码和产出 factor_values。

Truth Agent:
  只负责逐点真值比对。

AMR Agent:
  只负责审核和提出 patch，不允许直接改 Hermes 产物。

Promotion Agent:
  只负责按 registry policy 入库。
```

新增模块：

```text
agents/upload_agent.md
agents/truth_compare_agent.md
agents/reproduction_agent.md
agents/amr_review_agent.md
agents/promotion_agent.md
flows/factor_intake_flow.json
```

### 2.4 AutoGen：多 Agent 对话、人类代理、终止条件

可借鉴点：

```text
1. 多 Agent 之间不要无限聊天，要有终止条件。
2. 人只作为 UserProxy / HumanProxy 在异常点介入。
3. 每次交接要有明确消息结构。
4. 系统需要知道什么时候停止，而不是一直让 Agent 修。
```

映射到 Factor Lab：

```text
max_attempts: 3
termination_reason:
  passed
  failed
  not_comparable
  needs_review
  criteria_tampered
  max_attempts_exceeded
```

新增模块：

```text
attempt_policy.json
human_queue.json
handoff_message.schema.json
termination_policy.json
```

### 2.5 MCP：工具发现、资源发现、提示词标准化

可借鉴点：

```text
1. Agent 不应该靠猜工具名。
2. 系统应该向 Agent 暴露 tools、resources、prompts。
3. 工具是可调用动作，资源是可读取上下文，prompt 是标准操作规程。
```

映射到 Factor Lab：

```text
Tools:
  factor_lab.get_schema
  factor_lab.init_package
  factor_lab.validate_package
  factor_lab.submit_package
  factor_lab.get_task_status
  factor_lab.list_factor_registry

Resources:
  factor_lab://contracts/truth_compare
  factor_lab://contracts/research_reproduction
  factor_lab://registry/factor_families
  factor_lab://examples/truth_compare_package

Prompts:
  factor_lab_truth_compare_prompt
  factor_lab_research_upload_prompt
  factor_lab_repair_failed_submission_prompt
```

新增模块：

```text
mcp/factor_lab_server.py
mcp/resources/
mcp/prompts/
```

## 3. 推荐后的 Factor Lab 目标架构

```text
Agent / 人
  |
  v
Factor Lab Agent Adapter
  - JSON Schema
  - CLI
  - MCP Server
  - Guardrails
  - Repair Hints
  |
  v
Factor Lab Backend Intake
  - truth-compare
  - research-reproduction
  |
  v
Quarantine Task Workspace
  - request.json
  - status.json
  - criteria.json
  - gate_events.jsonl
  - checkpoints/
  - artifacts/
  |
  v
Specialized Agents
  - Truth Agent
  - Reproduction Agent
  - AMR Agent
  - Promotion Agent
  |
  v
Registry / Supabase / Dashboard
```

## 4. 应该加到项目里的模块

### 4.1 机器可读契约层

新增：

```text
contracts/
  truth_compare.schema.json
  research_reproduction.schema.json
  factor_values_csv.schema.json
  dashboard_factor.schema.json
  task_status.schema.json
  handoff_message.schema.json
  error_response.schema.json
```

作用：

```text
README 给人看。
JSON Schema 给 Agent、CLI、后端和 CI 用。
```

最小规则：

```text
1. 所有入口必须先 validate schema。
2. schema 不通过不能 submit。
3. 后端不能相信 Agent 自己声称“我符合契约”，必须重新校验。
```

### 4.2 Agent 友好的 CLI

新增：

```bash
factor-lab schema truth-compare
factor-lab init truth-compare --family wq101 --name alpha1
factor-lab init research-reproduction --name my_factor
factor-lab validate ./pkg
factor-lab submit ./pkg
factor-lab status <task_id>
factor-lab doctor
```

作用：

```text
让 Agent 不用自己猜目录结构。
让同事也能用同一套入口。
让错误修复变成命令行可自动化动作。
```

### 4.3 结构化错误与 repair_hint

所有接口错误必须返回：

```json
{
  "error_code": "missing_required_file",
  "message": "research-reproduction requires paper.pdf",
  "repair_hint": "Put paper.pdf in the package root and rerun factor-lab validate.",
  "retryable": true,
  "docs": "contracts/research_reproduction.schema.json"
}
```

Agent 看到 `repair_hint` 后可以自动修复，而不是去网络上乱找方案。

### 4.4 Gate event log

新增：

```text
gate_events.jsonl
```

每行一个事件：

```json
{
  "event_id": "evt_001",
  "task_id": "task_xxx",
  "gate": "G1",
  "actor": "upload_agent",
  "action": "validate_package",
  "status": "passed",
  "input_hash": "sha256:...",
  "output_hash": "sha256:...",
  "created_at": "2026-07-21T10:00:00+08:00"
}
```

作用：

```text
追踪 Agent 有没有绕开步骤。
定位哪一步跑偏。
给老板/审计看证据链。
```

### 4.5 Checkpoint / Resume

新增：

```text
checkpoints/
  G0.json
  G1.json
  G2.json
```

接口：

```text
GET  /api/agents/factor-lab/agent-tasks/<task_id>/checkpoints
POST /api/agents/factor-lab/agent-tasks/<task_id>/resume
POST /api/agents/factor-lab/agent-tasks/<task_id>/retry-gate
```

作用：

```text
跑失败不用从头开始。
人工介入后可以从指定 Gate 继续。
Agent 多次尝试可以留痕。
```

### 4.6 Quarantine 外部资料隔离

Agent 从网络、论文库、网页抓来的东西必须进入隔离区：

```json
{
  "source_type": "web",
  "source_url": "https://...",
  "fetched_at": "2026-07-21T10:00:00+08:00",
  "content_hash": "sha256:...",
  "license_note": "unknown",
  "quarantine": true
}
```

规则：

```text
1. quarantine=true 的材料不能直接 promotion。
2. 没有 source_url / content_hash 的外部材料不能进入正式任务。
3. 外部材料只能作为 research-reproduction 输入，不可直接写 factor_registry。
```

### 4.7 Tool allowlist

每个 Agent 只能调用自己的工具。

```text
Upload Agent:
  get_schema
  init_package
  validate_package
  submit_package

Truth Agent:
  get_truth_reference
  compare_values
  write_truth_report

Reproduction Agent:
  read_research_package
  run_reproduction
  write_hermes_out

AMR Agent:
  read_hermes_out
  write_review
  suggest_patch

Promotion Agent:
  read_final_decision
  write_registry
  write_public_dashboard
```

禁止：

```text
普通 Agent 直接写 Supabase public_dashboard_*。
AMR 直接覆盖 Hermes 的 factor.py。
Reproduction Agent 修改 criteria.json。
```

### 4.8 Human queue

人不在流程顶端，而在异常队列中。

触发条件：

```text
unknown_factor_family
criteria_tampered
schema_invalid_after_repair
max_attempts_exceeded
amr_suggested_patch
promotion_policy=human_confirm
external_source_license_unknown
```

队列字段：

```json
{
  "task_id": "task_xxx",
  "reason": "unknown_factor_family",
  "recommended_action": "register_factor_family_or_reject",
  "blocking": true,
  "created_at": "2026-07-21T10:00:00+08:00"
}
```

### 4.9 Agent observability 面板

前端可以新增一个只读页面：

```text
Agent 运行监控
```

展示：

```text
task_id
current_gate
actor
attempt_count
last_error_code
repair_hint
criteria_sha256_status
external_sources_count
human_queue_status
```

这不是给 Agent 用 GUI，而是给人看 Agent 有没有按框架走。

### 4.10 成本与安全限制

配置：

```json
{
  "max_web_fetches_per_task": 5,
  "max_attempts": 3,
  "max_package_size_mb": 200,
  "max_runtime_minutes": 30,
  "allow_direct_supabase_write": false,
  "require_source_hash": true
}
```

作用：

```text
限制 Agent 无限跑、无限抓、无限重试。
```

## 5. 优先级建议

### P0：必须先做

```text
1. contracts/*.schema.json
2. factor-lab validate / submit CLI
3. 结构化 error_code + repair_hint
4. 后端二次 schema 校验
5. gate_events.jsonl
```

原因：

```text
这五个直接解决 Agent 跑偏和提交不规范的问题。
```

### P1：接 Agent 前做

```text
1. MCP Server
2. Tool allowlist
3. Checkpoint / Resume
4. Human queue
5. external source quarantine
```

原因：

```text
这五个让 Agent 真正可控、可恢复、可审计。
```

### P2：规模化后做

```text
1. Agent observability 面板
2. 成本限制和运行配额
3. RBAC / 权限分层
4. 长期 memory / registry knowledge store
5. 自动回放测试集
```

原因：

```text
这些适合多人、多 Agent、多任务之后再强化。
```

## 6. 对现有系统的具体改法

### 6.1 当前已有

```text
1. 两个入口：
   /api/agents/factor-lab/intake/truth-compare
   /api/agents/factor-lab/intake/research-reproduction

2. criteria.json + criteria_sha256

3. request.json / status.json / artifacts/

4. Supabase public_dashboard_* 只读展示表设计

5. scripts/submit_factor_lab_intake.py 上传脚本
```

### 6.2 需要补齐

```text
1. 把上传契约从 README 提升为 JSON Schema。
2. submit 脚本升级为 factor-lab CLI。
3. 后端 intake 创建任务时写 gate_events.jsonl。
4. 所有错误改成 error_code + repair_hint。
5. 增加 MCP Server，让外部 Agent 自动发现 Factor Lab 能力。
6. 给外部来源增加 source_hash / source_url / quarantine 字段。
7. 增加 human_queue 表或 JSON 文件。
```

## 7. 给老师/老板的总结

成熟 Agent 框架共同点不是“模型更聪明”，而是：

```text
1. 状态显式化。
2. 工具显式化。
3. 契约机器可读。
4. 每一步有持久化。
5. 每一步可审计。
6. 人只处理异常。
7. 错误可修复。
8. 不合规结果不能进入生产。
```

Factor Lab 应该吸收这些结构，把平台变成 Agent 的默认路径：

```text
Agent 想完成任务，走 Factor Lab 最快。
Agent 即使绕开，结果也进不了库。
```

## 8. 参考来源

- LangGraph Persistence: https://docs.langchain.com/oss/python/langgraph/persistence
- OpenAI Agents SDK Guardrails: https://openai.github.io/openai-agents-python/guardrails/
- CrewAI Documentation: https://docs.crewai.com/
- Microsoft AutoGen Human-in-the-Loop: https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/tutorial/human-in-the-loop.html
- Model Context Protocol Server Concepts: https://modelcontextprotocol.io/docs/learn/server-concepts
