# Factor Lab Supabase 统一入口 V1

本文档定义 Supabase 里的统一数据入口。目标是：同事、后端、Agent 都按同一套格式提交，前端永远只读固定的 `public_dashboard_*` 对象。

## 一句话原则

不要让前端适配每个同事临时建的表。所有数据先进入 staging，再标准化，再发布到 dashboard。

```text
同事 / Agent / 本地后端
  -> factor_import_batches
  -> factor_values_staging / factor_metric_staging
  -> normalize_factor_import_batch()
  -> factor_values / factor_truth_values / factor_metrics
  -> public_dashboard_factors / public_dashboard_factor_*
  -> GitHub Pages 前端只读展示
```

## 1. 老板先跑建表 SQL

在 Supabase 控制台打开：

```text
SQL Editor -> New query
```

粘贴并执行：

```text
supabase/factor_lab_unified_entry_v1.sql
```

这份 SQL 会创建：

| 层级 | 表 / 视图 | 用途 |
|---|---|---|
| 批次 | `factor_import_batches` | 每次上传一条 batch 记录，记录来源、因子族、版本、提交人 |
| 暂存 | `factor_values_staging` | 接收标准 CSV 因子值 |
| 暂存 | `factor_metric_staging` | 接收 IC/IR/覆盖率等指标 |
| 标准 | `factor_values` | 统一因子值明细，支持 truth/submitted/reproduced/research |
| 标准 | `factor_truth_values` | 兼容当前真值对照逻辑的真值表 |
| 标准 | `factor_metrics` | 统一指标表，放 IC/IR/覆盖率/多空收益 |
| 展示 | `public_dashboard_factors` | 当前前端主表，只读公开 |
| 展示 | `public_dashboard_factor_values_summary` | 因子值摘要视图 |
| 展示 | `public_dashboard_factor_metrics` | 因子指标视图 |

## 2. 统一 CSV 格式

同事提交因子值时，CSV 必须至少包含三列：

```csv
symbol,trade_date,value
003016.XSHE,2020-11-02,-0.984138785625
003016.XSHE,2020-11-03,-0.872893954410
```

可选列：

```csv
value_type,source_version
```

字段含义：

| 字段 | 必填 | 说明 |
|---|---:|---|
| `symbol` | 是 | 股票代码，统一用 `003016.XSHE` 这种格式 |
| `trade_date` | 是 | 交易日，格式 `YYYY-MM-DD` |
| `value` | 是 | 因子值 |
| `value_type` | 否 | `truth` / `submitted` / `reproduced` / `research` |
| `source_version` | 否 | 默认 `v1` |

`value_type` 口径：

| value_type | 用途 |
|---|---|
| `truth` | 因子库标准真值，可用于逐点真值对照 |
| `submitted` | 用户提交的一份待对照因子值 |
| `reproduced` | Hermes/Agent 复现出来的因子值 |
| `research` | 研报论文复现线里的研究结果值 |

## 3. 指标 JSON 格式

如果已经算出了 IC/IR/覆盖率，需要额外提交一个 JSON：

```json
{
  "factor_family": "alpha101",
  "factor_name": "WorldQuant_alpha013",
  "library": "WQ101",
  "category": "量价因子",
  "market": "A股",
  "status": "candidate",
  "proof_status": "passed",
  "truth_status": "not_compared",
  "overall_status": "passed",
  "coverage_ratio": 0.9833,
  "rank_ic_mean": 0.0244,
  "rank_ic_ir": 0.0959,
  "ic_mean": 0.0244,
  "ic_ir": 0.0959,
  "long_short_mean": 0.0074,
  "turnover": null,
  "start_date": "2016-01-04",
  "end_date": "2026-07-06",
  "metadata": {
    "source": "factor_lab_local_eval",
    "note": "IC/IR computed locally and published through unified intake"
  }
}
```

重要：Supabase 原始表里的 `value` 是因子值，不是 IC。IC/IR 必须由本地硬代码或后端计算后写入 `factor_metric_staging`。

## 4. 本地脚本提交方式

先设置环境变量：

```powershell
$env:FACTOR_LAB_SUPABASE_URL="https://你的项目.supabase.co"
$env:FACTOR_LAB_SUPABASE_WRITE_KEY="service_role 或 authenticated JWT"
```

然后提交因子值：

```powershell
python scripts/submit_supabase_unified_factor.py `
  --values-csv C:\path\alpha013_values.csv `
  --metrics-json C:\path\alpha013_metrics.json `
  --entry-type truth_compare `
  --factor-family alpha101 `
  --factor-name WorldQuant_alpha013 `
  --library WQ101 `
  --source-name Alpha101因子13_part1 `
  --source-version v1 `
  --value-type truth `
  --submitted-by intern_name
```

脚本会自动执行：

```text
1. 写 factor_import_batches
2. 写 factor_values_staging
3. 写 factor_metric_staging
4. 调 normalize_factor_import_batch(batch_id, true)
5. 发布到 public_dashboard_factors
```

如果只想先入标准表、不展示到前端，加：

```powershell
--no-publish
```

## 5. Agent 接入规则

Agent 只能写 staging 或调用统一入口函数，不允许直接写前端表。

允许：

```text
factor_import_batches
factor_values_staging
factor_metric_staging
normalize_factor_import_batch()
```

禁止：

```text
直接写 public_dashboard_factors
直接让前端读取临时表
每个因子单独新建一张表
```

## 6. 前端读取规则

GitHub Pages 前端只读：

```text
public_dashboard_factors
public_dashboard_factor_values_summary
public_dashboard_factor_metrics
factor_truth_values_summary
```

前端不要读取：

```text
Alpha101因子13 part1
factor_values_staging
factor_metric_staging
factor_values
factor_truth_values
factor_metrics
```

这样以后同事新增表、Agent 复现、研报线提交，都不会再要求改前端。

## 7. 权限规则

浏览器里只能放 publishable / anon key，只能 SELECT 公开视图。

写入必须走：

```text
本地后端
Agent CLI
公司服务器
Supabase Auth authenticated user
service_role key
```

不要把 `service_role`、数据库密码、Storage 私有签名密钥放进 GitHub Pages。

## 8. 老表如何接入

如果同事已经建了临时表，比如：

```text
public."Alpha101因子13 part1"
```

不要让前端直接读它。做法是把它导入 staging：

```sql
insert into public.factor_import_batches (
  entry_type,
  factor_family,
  factor_name,
  library,
  source_name,
  source_version,
  submitted_by
) values (
  'legacy_table_import',
  'alpha101',
  'WorldQuant_alpha013',
  'WQ101',
  'Alpha101因子13 part1',
  'v1',
  'intern'
)
returning batch_id;
```

拿到 `batch_id` 后：

```sql
insert into public.factor_values_staging (
  batch_id,
  factor_family,
  factor_name,
  symbol,
  trade_date,
  value,
  value_type,
  source_version,
  raw_payload
)
select
  '<上一步返回的 batch_id>'::uuid,
  'alpha101',
  trim(factor),
  trim(order_book_id),
  to_date(trim(date), 'YYYY-MM-DD'),
  value::double precision,
  'truth',
  'v1',
  jsonb_build_object('source_table', 'Alpha101因子13 part1')
from public."Alpha101因子13 part1";
```

最后：

```sql
select public.normalize_factor_import_batch('<batch_id>'::uuid, true);
```

## 9. 给老板的口径

可以这样说：

> 我已经把 Supabase 入口统一成 batch + staging + canonical + dashboard 四层。以后同事和 Agent 只需要按固定 CSV/JSON 格式提交到 staging，由 `normalize_factor_import_batch()` 统一清洗、去重、入标准表并发布到前端。前端不再适配任何临时表，只读 `public_dashboard_*`，这样数据格式、权限和展示路径都固定了。
