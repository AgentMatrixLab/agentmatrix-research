# Factor Lab Colleague Submission

同事提交只允许走两个官方 intake 路径：

```text
1. truth-compare
   已有因子值 -> 和因子库标准真值逐点比对

2. research-reproduction
   论文 / 研报 / 代码 / 实验数据 -> 复现为可运行、可审核、可入库的候选因子
```

不要让同事直接写 `public_dashboard_factors`，也不要把结果包绕过审核直接推到展示表。展示表只应由后端 / Agent 在完成审核和 promotion 后写入。

## 1. 真值对照提交包

适用场景：用户已经有一份因子值，需要回答“这份值能不能和库里的标准真值对上、覆盖率多少、误差多少、是不是重复因子”。

目录固定为：

```text
truth_compare_YYYYMMDD_name/
  manifest.json
  factor_values.csv
```

`manifest.json` 固定字段：

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

`factor_values.csv` 固定列：

```csv
date,symbol,factor_value
2024-01-02,000001.SZ,0.123
2024-01-02,000002.SZ,-0.456
```

提交命令：

```bash
python scripts/submit_factor_lab_intake.py truth-compare submissions/truth_compare_YYYYMMDD_name --dry-run
python scripts/submit_factor_lab_intake.py truth-compare submissions/truth_compare_YYYYMMDD_name
```

## 2. 研报论文复现提交包

适用场景：用户提交研究材料，目标是复现出候选因子。这个路径不强制要求真值，因为很多研报本来没有可逐点对照的标准值。

目录固定为：

```text
research_reproduction_YYYYMMDD_name/
  manifest.json
  code.py
  experiment_data.csv
  paper.pdf
  research_report.pdf
  truth_values.csv          # 可选；有就做诊断，不作为研报入口的硬前提
```

`manifest.json` 固定字段：

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

固定主文件：

```text
code.py
experiment_data.csv
paper.pdf
research_report.pdf
```

提交命令：

```bash
python scripts/submit_factor_lab_intake.py research-reproduction submissions/research_reproduction_YYYYMMDD_name --dry-run
python scripts/submit_factor_lab_intake.py research-reproduction submissions/research_reproduction_YYYYMMDD_name
```

## 3. 后端地址

默认提交到本地后端：

```text
http://127.0.0.1:8012
```

如果后端部署到云端：

```bash
python scripts/submit_factor_lab_intake.py truth-compare submissions/pkg --api https://your-factor-lab-api.example.com
```

也可以在 `.env.local` 设置：

```text
FACTOR_LAB_API_HOST=http://127.0.0.1:8012
```

## 4. 权限边界

同事只需要：

```text
提交包模板
scripts/submit_factor_lab_intake.py
Factor Lab 后端地址
```

同事不需要：

```text
Supabase secret key
Supabase service role key
数据库密码
直接写 public_dashboard_* 表的权限
```

## 5. 流程结果

脚本只创建 intake 任务：

```text
truth-compare -> /api/agents/factor-lab/intake/truth-compare
research-reproduction -> /api/agents/factor-lab/intake/research-reproduction
```

任务进入后端后，会生成：

```text
runtime/factor_lab/agent_tasks/<task_id>/
  request.json
  status.json
  artifacts/
```

后续由 Agent 执行、审核、promotion，再写 Supabase 展示表。前端只读 Supabase 的公开展示表，不承担审核和入库职责。
