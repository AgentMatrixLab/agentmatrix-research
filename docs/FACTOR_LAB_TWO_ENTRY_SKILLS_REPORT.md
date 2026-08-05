# Factor Lab 两入口上传流程报告

本文档只定义“上传流程”，不定义论文复现、AMR 审核、回测、入库等下游流程。论文复现链路由专门同事负责；本模块只负责把同事提交的材料按固定契约送进后端任务队列。

当前只保留两个上传入口：

```text
入口一：truth-compare
已有因子值上传，用于和库内标准真值对照。

入口二：research-reproduction
研报 / 论文 / 代码 / 实验数据上传，用于交给下游论文复现链路处理。
```

不设置第三个“展示打包”入口。Supabase 展示表只读，不允许同事直接写入。

## 1. 上传链路总览

```text
人选择入口
  -> 准备固定文件夹
  -> 本地 CLI 校验
  -> CLI 生成标准 payload
  -> POST 到 Factor Lab 后端
  -> 后端生成 task_id / request.json / status.json
  -> 下游 Agent 或同事接管任务
```

本模块的边界到“后端成功创建 intake task”为止。

## 2. 当前接口

### 真值对照上传接口

```text
POST /api/agents/factor-lab/intake/truth-compare
```

CLI entry：

```text
truth-compare
```

标准化字段：

```json
{
  "task_type": "truth_compare",
  "skill_name": "truth_compare_v1"
}
```

### 研报复现上传接口

```text
POST /api/agents/factor-lab/intake/research-reproduction
```

CLI entry：

```text
research-reproduction
```

标准化字段：

```json
{
  "task_type": "research_reproduction",
  "skill_name": "research_reproduction_v1"
}
```

## 3. 上传 Skill 设计

这里的 Skill 只服务上传流程，不执行论文复现和真值计算。

### Upload Skill 1：entry_selection_v1

目的：确定用户选择哪一个上传入口。

人工操作：

```text
如果用户已有一份因子值，需要和库内标准真值对照，选择 truth-compare。
如果用户提交研报、论文、代码、实验数据，选择 research-reproduction。
```

输入：

```json
{
  "entry": "truth-compare | research-reproduction"
}
```

输出：

```json
{
  "skill_name": "entry_selection_v1",
  "entry": "truth-compare",
  "task_type": "truth_compare",
  "endpoint": "/api/agents/factor-lab/intake/truth-compare"
}
```

接口对照：

| entry | task_type | endpoint |
| --- | --- | --- |
| `truth-compare` | `truth_compare` | `/api/agents/factor-lab/intake/truth-compare` |
| `research-reproduction` | `research_reproduction` | `/api/agents/factor-lab/intake/research-reproduction` |

### Upload Skill 2：folder_contract_check_v1

目的：校验用户提交的文件夹是否符合入口契约。

真值对照文件夹：

```text
truth_compare_YYYYMMDD_name/
  manifest.json
  factor_values.csv
```

研报复现文件夹：

```text
research_reproduction_YYYYMMDD_name/
  manifest.json
  code.py
  experiment_data.csv
  paper.pdf
  research_report.pdf
  truth_values.csv          # 可选
```

校验规则：

```text
1. 文件夹必须存在
2. manifest.json 必须存在
3. truth-compare 必须有 factor_values.csv
4. research-reproduction 必须有 code.py、experiment_data.csv、paper.pdf、research_report.pdf
5. manifest.task_type 如果填写，必须和入口匹配
6. truth-compare 必须填写 factor_family 和 factor_name
```

输出：

```json
{
  "skill_name": "folder_contract_check_v1",
  "status": "passed",
  "entry": "truth-compare",
  "required_files_present": true,
  "missing_files": []
}
```

接口对照：

| 校验结果 | 对应 payload 字段 |
| --- | --- |
| `required_files_present=true` | `package.required_files` |
| `missing_files=[]` | 允许继续生成 payload |
| `factor_family/factor_name` | `payload.factor_family` / `payload.factor_name` |

### Upload Skill 3：manifest_normalization_v1

目的：读取 `manifest.json`，把用户填写的信息规范化成后端统一字段。

真值对照 manifest 示例：

```json
{
  "task_type": "truth_compare",
  "submitter": "name",
  "factor_family": "wq101",
  "factor_name": "alpha1",
  "package_name": "truth_compare_YYYYMMDD_alpha1",
  "created_at": "2026-07-17T10:00:00+08:00",
  "data_source": "quant_api",
  "requires_quant_api": true,
  "notes": []
}
```

研报复现 manifest 示例：

```json
{
  "task_type": "research_reproduction",
  "submitter": "name",
  "factor_family": "exploratory",
  "factor_name": "research_factor_name",
  "package_name": "research_reproduction_YYYYMMDD_name",
  "created_at": "2026-07-17T10:00:00+08:00",
  "data_source": "quant_api",
  "requires_quant_api": true,
  "notes": []
}
```

输出：

```json
{
  "skill_name": "manifest_normalization_v1",
  "status": "passed",
  "submitter": "name",
  "factor_family": "wq101",
  "factor_name": "alpha1",
  "package_name": "truth_compare_YYYYMMDD_alpha1",
  "data_source": "quant_api",
  "requires_quant_api": true
}
```

接口对照：

| manifest 字段 | payload 字段 |
| --- | --- |
| `submitter` | `submitter` |
| `factor_family` | `factor_family` |
| `factor_name` | `factor_name` |
| `package_name` | `package.package_name` |
| `created_at` | `requested_at` |
| `notes` | `submission_notes` |

### Upload Skill 4：file_inventory_v1

目的：扫描提交文件夹，生成后端可读的文件清单。

输出：

```json
{
  "skill_name": "file_inventory_v1",
  "status": "passed",
  "files": [
    {
      "name": "factor_values.csv",
      "relative_path": "example_truth_compare_submission/factor_values.csv",
      "size": 80,
      "type": "application/vnd.ms-excel",
      "last_modified": "2026-07-17T09:01:44.782605+00:00"
    }
  ]
}
```

接口对照：

| 文件清单字段 | payload 字段 |
| --- | --- |
| `name` | `files[].name` |
| `relative_path` | `files[].relative_path` |
| `size` | `files[].size` |
| `type` | `files[].type` |
| `last_modified` | `files[].last_modified` |

### Upload Skill 5：payload_build_v1

目的：把入口、manifest 和文件清单组装成标准后端 payload。

真值对照 payload 结构：

```json
{
  "schema_version": "factor_intake_request_v1",
  "task_type": "truth_compare",
  "skill_name": "truth_compare_v1",
  "factor_family": "wq101",
  "factor_name": "alpha1",
  "package": {
    "input_mode": "folder",
    "package_name": "truth_compare_YYYYMMDD_alpha1",
    "required_files": ["factor_values.csv"],
    "files": []
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

研报复现 payload 结构：

```json
{
  "schema_version": "factor_intake_request_v1",
  "task_type": "research_reproduction",
  "skill_name": "research_reproduction_v1",
  "package": {
    "input_mode": "folder",
    "package_name": "research_reproduction_YYYYMMDD_name",
    "required_files": [
      "code.py",
      "experiment_data.csv",
      "paper.pdf",
      "research_report.pdf"
    ],
    "files": []
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

接口对照：

| payload 字段 | 后端作用 |
| --- | --- |
| `schema_version` | 标记 intake request 版本 |
| `task_type` | 后端选择任务路径 |
| `skill_name` | 后端记录入口 skill |
| `package.required_files` | 后端知道本任务必需文件 |
| `files[]` | 后端记录上传包文件清单 |
| `human_policy` | 标记中间过程不要求人交互 |

### Upload Skill 6：backend_submit_v1

目的：把标准 payload 提交给 Factor Lab 后端。

执行命令：

```bash
python scripts/submit_factor_lab_intake.py truth-compare submissions/example_truth_compare_submission
```

或：

```bash
python scripts/submit_factor_lab_intake.py research-reproduction submissions/example_research_reproduction_submission
```

如果后端不在本机：

```bash
python scripts/submit_factor_lab_intake.py truth-compare submissions/pkg --api https://your-factor-lab-api.example.com
```

输出：

```json
{
  "skill_name": "backend_submit_v1",
  "status": "submitted",
  "endpoint": "http://127.0.0.1:8012/api/agents/factor-lab/intake/truth-compare",
  "task_id": "<task_id>",
  "request_path": "runtime/factor_lab/agent_tasks/<task_id>/request.json",
  "status_path": "runtime/factor_lab/agent_tasks/<task_id>/status.json"
}
```

接口对照：

| CLI entry | POST endpoint |
| --- | --- |
| `truth-compare` | `/api/agents/factor-lab/intake/truth-compare` |
| `research-reproduction` | `/api/agents/factor-lab/intake/research-reproduction` |

### Upload Skill 7：task_receipt_v1

目的：把后端返回结果整理成同事能看懂的提交回执。

输出：

```json
{
  "skill_name": "task_receipt_v1",
  "accepted_by_backend": true,
  "task_id": "<task_id>",
  "task_type": "truth_compare",
  "status": "queued",
  "next_owner": "downstream_agent_or_reproduction_owner"
}
```

接口对照：

| 回执字段 | 后端返回字段 |
| --- | --- |
| `task_id` | `task_id` |
| `status` | `status` |
| `request_path` | `request_path` |
| `status_path` | `status_path` |

## 4. 两个入口的上传差异

| 项目 | 真值对照上传 | 研报复现上传 |
| --- | --- | --- |
| CLI entry | `truth-compare` | `research-reproduction` |
| 后端 task_type | `truth_compare` | `research_reproduction` |
| 后端 skill_name | `truth_compare_v1` | `research_reproduction_v1` |
| 必需文件 | `factor_values.csv` | `code.py`, `experiment_data.csv`, `paper.pdf`, `research_report.pdf` |
| 可选文件 | 无 | `truth_values.csv`, `truth_values.parquet` |
| 上传后归属 | 真值对照后端链路 | 论文复现负责同事 / 下游 Agent |
| Supabase | 不直接写 | 不直接写 |

## 5. 同事实际操作步骤

### 5.1 准备真值对照上传包

```text
submissions/truth_compare_YYYYMMDD_name/
  manifest.json
  factor_values.csv
```

先 dry-run：

```bash
python scripts/submit_factor_lab_intake.py truth-compare submissions/truth_compare_YYYYMMDD_name --dry-run
```

确认无误后提交：

```bash
python scripts/submit_factor_lab_intake.py truth-compare submissions/truth_compare_YYYYMMDD_name
```

### 5.2 准备研报复现上传包

```text
submissions/research_reproduction_YYYYMMDD_name/
  manifest.json
  code.py
  experiment_data.csv
  paper.pdf
  research_report.pdf
```

先 dry-run：

```bash
python scripts/submit_factor_lab_intake.py research-reproduction submissions/research_reproduction_YYYYMMDD_name --dry-run
```

确认无误后提交：

```bash
python scripts/submit_factor_lab_intake.py research-reproduction submissions/research_reproduction_YYYYMMDD_name
```

## 6. dry-run 输出对照

### 真值对照 dry-run 应看到

```json
{
  "dry_run": true,
  "entry": "truth-compare",
  "task_type": "truth_compare",
  "skill_name": "truth_compare_v1",
  "files": [
    "factor_values.csv",
    "manifest.json"
  ]
}
```

### 研报复现 dry-run 应看到

```json
{
  "dry_run": true,
  "entry": "research-reproduction",
  "task_type": "research_reproduction",
  "skill_name": "research_reproduction_v1",
  "files": [
    "code.py",
    "experiment_data.csv",
    "manifest.json",
    "paper.pdf",
    "research_report.pdf"
  ]
}
```

## 7. 给老板看的结论

当前这部分只解决“上传入口标准化”：

```text
同事不需要知道 Supabase、不需要数据库权限、不需要 GUI。
同事只需要按两个固定文件夹契约准备材料，然后用 CLI 提交到后端。
后端创建标准 intake task 后，下游 Agent 或负责复现的同事再接管。
```

这样做的好处：

```text
1. 上传入口清楚，只有两条路径。
2. 文件结构固定，后端好对接。
3. 同事不直接写 Supabase，权限风险低。
4. 论文复现内部流程可以由另一个同事独立演进，不影响上传入口。
5. 前端只负责展示审核后的结果，不承担上传和复现逻辑。
```
