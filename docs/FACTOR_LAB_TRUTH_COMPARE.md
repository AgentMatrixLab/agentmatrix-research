# Factor Lab 真值对照（Truth Compare）使用与测试说明

> 对应入口一：用户上传因子值，与因子库标准真值逐点比对，回答"对不对得上、是否重复因子、误差与覆盖率多少"。
> 本文档同时覆盖：**本地自测方法（无需任何 Supabase 权限）** 与 **项目组 Supabase 集成所需的一切配置**。

## 1. 功能概述

- 输入：一份"用户上传"的因子值 CSV（长表，含 `date` / `symbol` / `factor_value` 列，列名兼容 `trade_date` / `code` / 具体因子名）。
- 真值来源（按优先级）：
  1. 本地真值宽表 CSV（`--truth-csv` 指定，行为 `date, code, alpha1, ..., alpha101`）；
  2. Supabase 表 `factor_truth_values`（配置了环境变量时自动回退）。
- 判定逻辑（默认值，可用参数覆盖）：
  - `overlap_ratio >= 0.9`（上传值与真值的键覆盖率，`--min-overlap`）；
  - `exact_match_ratio >= 0.99`（逐点命中率，`--pass-exact`）；
  - `max_abs_error <= 1e-8`（容差，`--tolerance`）。
- 三种结果状态：
  - `passed` → decision = `accept`（建议复用/入库）；
  - `failed` → decision = `reject`（附具体未通过原因与最多 12 条 mismatch 样本）；
  - `not_comparable` → 库内无该因子标准真值，无法对照。

## 2. 本地测试（无需 Supabase、无需任何 key）

以下步骤完全离线，所有中间产物写入 `data/factor_lab/` 与 `runtime/factor_lab/`，这两个目录已在 `.gitignore` 中，**不会也不应被提交**。

### Step 1 — 生成本地标准真值模板（60 天 × 5 只股票）

```bash
python -m research_core.factor_lab.cli export-alpha101-truth-template --n-dates 60 --n-codes 5 --seed 29
```

生成 `data/factor_lab/alpha101_truth_template_101f_60d_5c_s29.csv`（宽表，含 alpha1–alpha101 共 101 列）。

### Step 2 — 构造"用户上传"测试样本

```bash
python scripts/dev/make_truth_compare_samples.py
```

从真值模板抽出 alpha1 一列，生成两份样本到 `data/factor_lab/samples/`：

| 样本文件 | 构造方式 | 预期对照结果 |
| --- | --- | --- |
| `factor_values_alpha1_pass.csv` | 原样抽取真值 | `passed`（exact_match_ratio = 1.0） |
| `factor_values_alpha1_perturbed.csv` | 整体 ×1.5 + 0.001 扰动 | `failed`（误差远超容差） |

### Step 3 — 跑 passed 分支

```bash
python scripts/run_truth_compare.py \
  --factor-family alpha101 \
  --factor-name alpha1 \
  --values-csv data/factor_lab/samples/factor_values_alpha1_pass.csv \
  --truth-csv data/factor_lab/alpha101_truth_template_101f_60d_5c_s29.csv
```

预期输出：

```text
STATUS        : passed  ->  decision: accept
exact_match   : 1.0000
max_abs_error : 0.0
```

### Step 4 — 跑 failed 分支

把 `--values-csv` 换成 `factor_values_alpha1_perturbed.csv`，其余不变。预期：

```text
STATUS        : failed  ->  decision: reject
reasons       : ['exact_match_ratio=... < pass_exact_match_ratio=0.99', 'max_abs_error=... > tolerance=1e-08']
```

### Step 5 — 跑 not_comparable 分支

把 `--factor-name` 换成库内不存在的名字（如 `alpha999`），真值表里没有该列，预期：

```text
STATUS        : not_comparable  ->  decision: reject
reasons       : ['no_library_truth']
```

### Step 6 — 检查产物

每次运行生成 `runtime/factor_lab/truth_compare/truthcmp-<时间戳>/`，包含：

- `truth_comparison.json` — 完整对照指标（覆盖率、命中率、误差、截面相关性、mismatch 样本）；
- `final_decision.json` — 裁决结果与原因；
- `supabase_sync_payload.json` — 待同步到 Supabase 的幂等负载（见第 3 节）。

### Step 7 — 前端验证（可选）

```bash
python backend/factor_lab_api.py
# 打开 http://127.0.0.1:8012/factor-lab-dashboard
```

在任务列表提交 `truth_compare` 类型任务，或在跑对照时加 `--task-id <task_id>`，执行器会把结果写回该任务的 `status.json`，任务详情页会渲染"真值对照结果"面板（状态徽章、裁决、覆盖率、命中率、最大误差、产物目录）。

## 3. Supabase 集成（需要项目组配合的部分）

> 原则：能放进仓库的代码/SQL 已全部放在仓库里；**只有 key 需要项目组提供**，按下文占位配置即可，切勿把真实 key 提交进仓库。

### 3.1 需要执行的 SQL（按顺序，在 Supabase SQL Editor 或 `supabase db push`）

| 顺序 | 文件 | 作用 |
| --- | --- | --- |
| 1 | `supabase/factor_lab_unified_entry_v1.sql` | 建 `factor_truth_values` 真值表及 RLS（若已执行过可跳过，幂等） |
| 2 | `supabase/migrations/202607160001_factor_lab_dashboard.sql` | 建 `public_dashboard_factors` 看板表及公开读策略 |
| 3 | `supabase/migrations/202607290001_factor_truth_comparisons.sql` | **本次新增**：建 `factor_truth_comparisons` 对照结果表 + `public_dashboard_truth_comparisons` 公开只读视图 |
| 4（可选） | `supabase/import_alpha101_013_truth_values.sql` | 预置 alpha101 / alpha013 标准真值数据 |

所有脚本均幂等（`if not exists` / `create or replace`），可重复执行。

### 3.2 需要的 key（占位，需项目组提供）

复制 `.env.example` 为 `.env` 后填写，或直接 export 环境变量：

| 环境变量 | 需要的权限 | 说明 |
| --- | --- | --- |
| `FACTOR_LAB_SUPABASE_URL` | 无（项目公开 URL） | 形如 `https://<project-ref>.supabase.co` |
| `FACTOR_LAB_SUPABASE_WRITE_KEY` | **service_role**（需项目组提供） | 用于读取 `factor_truth_values` 真值表、写入 `factor_truth_comparisons` / `public_dashboard_factors`。表已开 RLS，anon key 无法写入 |

前端看板所需的 `FACTOR_LAB_SUPABASE_ANON_KEY`（publishable）为公开读 key，配置在 `frontend/factor-lab-dashboard/config.js` / `pages/factor-lab-dashboard/config.js`，只能 SELECT 公开视图，不需要额外权限。

### 3.3 同步对照结果到 Supabase

本地跑完对照（第 2 节 Step 3–5）后，每个 run 目录下已生成 `supabase_sync_payload.json`。配置好 3.2 的两个环境变量后：

```bash
# 同步所有未同步的 run
python scripts/sync_truth_compare_to_supabase.py

# 或只同步指定 run
python scripts/sync_truth_compare_to_supabase.py --run-dir runtime/factor_lab/truth_compare/truthcmp-<时间戳>
```

- 幂等：`factor_truth_comparisons.run_id` 有唯一约束，重复同步自动忽略；已同步的 run 会打 `_synced.json` 标记跳过。
- 写入两张表：`factor_truth_comparisons`（对照记录）与 `public_dashboard_factors`（看板因子真值状态汇总）。
- 不配 key 时脚本会直接提示缺变量并退出，不会影响本地对照流程。

### 3.4 从 Supabase 真值库抽样本（可选，需要 write key）

```bash
python scripts/dev/export_alpha013_slice.py
```

从 `factor_truth_values` 导出 alpha013 切片，构造"真实真值"场景的验收样本。

## 4. 本次 PR 改动清单

- `scripts/run_truth_compare.py`（新增）— 真值对照执行器（本地版）。
- `scripts/sync_truth_compare_to_supabase.py`（新增）— 对照结果同步到 Supabase（需 service key）。
- `scripts/dev/make_truth_compare_samples.py`（新增）— 自洽性测试样本生成器。
- `scripts/dev/export_alpha013_slice.py`（新增）— 从 Supabase 真值库导出验收样本。
- `supabase/migrations/202607290001_factor_truth_comparisons.sql`（新增）— 对照结果表 + 公开只读视图。
- `frontend/factor-lab-dashboard/app.js` / `styles.css` — 任务详情页新增"真值对照结果"面板；修正任务列表加载时序与 tasks 视图刷新。
- `pages/factor-lab-dashboard/` — GitHub Pages 静态镜像，与 frontend 同步。
