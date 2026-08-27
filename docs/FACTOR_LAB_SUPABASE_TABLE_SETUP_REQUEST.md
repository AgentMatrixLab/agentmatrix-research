# Factor Lab Supabase 建表与数据导入请求

本文档用于请有 Supabase 项目权限的同事，在公司 Supabase 项目中创建 Factor Lab 展示表，并导入当前本地生成的公开展示数据。

## 1. 当前状态

Factor Lab GitHub Pages 前端已经接入公司 Supabase：

```text
Supabase URL:
https://rebyrzrvnfbwvmbjvhzj.supabase.co

Frontend publishable key:
sb_publishable_ZHAM5wQWZh_Wng4TaL-fDg_XlFBcB6j
```

但当前我这边只有 `publishable key`。这个 key 只能用于前端读取公开表，不能建表、不能写表，也不能进入 Supabase SQL Editor。

因此需要有 Supabase 项目权限的人执行一次建表和导入。

## 2. 需要执行的 SQL 文件

请按顺序执行两个文件。

### 第一步：建表与 RLS 策略

文件：

```text
supabase/migrations/202607160001_factor_lab_dashboard.sql
```

作用：

```text
1. 创建 factor_registry
2. 创建 tasks / task_files
3. 创建 public_dashboard_tasks
4. 创建 public_dashboard_factors
5. 创建 public_dashboard_metrics
6. 创建 public_dashboard_reports
7. 创建 promotion_logs
8. 开启 Row Level Security
9. 允许 anon/authenticated 只读 public_dashboard_* 展示表
10. 创建 public-reports / private-inputs / private-artifacts storage buckets
```

安全边界：

```text
public_dashboard_* 表只开放 SELECT。
前端 publishable key 只能读这些公开展示表。
私有任务、文件、产物表不开放给 anon 写入。
```

### 第二步：导入本地 Factor Lab 展示数据

文件：

```text
supabase/seed_factor_lab_dashboard_from_local.sql
```

作用：

```text
把当前本地 Factor Lab 页面里的公开展示因子 upsert 到 public_dashboard_factors。
当前共 302 条展示记录。
```

导入方式是 `on conflict (factor_id) do update`，所以后续重复执行不会产生重复行，会按 `factor_id` 更新已有记录。

## 3. 操作步骤

1. 打开 Supabase 后台：

```text
https://supabase.com/dashboard/project/rebyrzrvnfbwvmbjvhzj
```

2. 进入：

```text
SQL Editor -> New query
```

3. 粘贴并运行：

```text
supabase/migrations/202607160001_factor_lab_dashboard.sql
```

4. 成功后，再新建一个 query，粘贴并运行：

```text
supabase/seed_factor_lab_dashboard_from_local.sql
```

5. 运行完成后，打开前端页面验证：

```text
https://miao050805-arch.github.io/agentmatrix-research/factor-lab-dashboard/
```

## 4. 验证方式

在 Supabase SQL Editor 里可以执行：

```sql
select count(*) from public.public_dashboard_factors;
```

预期结果：

```text
302
```

也可以执行：

```sql
select factor_id, factor_name, library, proof_status, truth_status, overall_status
from public.public_dashboard_factors
order by library, factor_name
limit 20;
```

预期能看到类似：

```text
WQ101:alpha1
WQ101:alpha2
...
GTJA191:alpha1
...
Alpha158:...
QuantAPI:...
```

## 5. 费用说明

这次导入的是页面展示用的 metadata，不是大文件。

当前导出的文件体积约为：

```text
SQL: 约 460 KB
JSON: 约 711 KB
记录数: 302
```

这类数据量很小。只要不把 parquet、PDF、研报原文、大型回测产物直接塞进 Postgres 表里，正常不会造成明显费用压力。

后续大文件应放：

```text
private-inputs
private-artifacts
public-reports
```

或者外部对象存储，不应直接写入表字段。

## 6. 如果需要我继续操作

如果希望我直接执行建表和导入，需要提供以下任一种权限：

```text
1. 把我加入 Supabase project / organization，让我可以进入 SQL Editor；
2. 给我真实的 Postgres database password；
3. 给后端使用的 Supabase service role / secret key。
```

注意：

```text
publishable key 不能用于建表或写表。
service role / secret key 不应放进前端，也不应发给普通同事。
```
