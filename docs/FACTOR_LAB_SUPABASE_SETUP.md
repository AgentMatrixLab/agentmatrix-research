# Factor Lab Supabase Setup

本文档说明当前过渡阶段的 Supabase 接入方式：Agent 和后端仍在本地运行，GitHub Pages 前端只读取 Supabase 的公开展示表。

## 1. 当前分工

```text
本地 Agent / 本地后端
  运行复现、审核、回测、promotion
  使用 service role 或数据库连接写 Supabase

Supabase
  存公开展示表、私有任务表、Storage bucket
  RLS 控制浏览器只能 SELECT 公开表

GitHub Pages
  静态展示
  使用 publishable / anon key 读取 public_dashboard_* 表
```

## 2. 建表

打开 Supabase 项目：

```text
https://rebyrzrvnfbwvmbjvhzj.supabase.co
```

进入：

```text
Supabase Dashboard -> SQL Editor -> New query
```

粘贴并执行：

```text
supabase/migrations/202607160001_factor_lab_dashboard.sql
```

这份 SQL 会创建：

- `factor_registry`
- `tasks`
- `task_files`
- `public_dashboard_tasks`
- `public_dashboard_factors`
- `public_dashboard_metrics`
- `public_dashboard_reports`
- `promotion_logs`
- Storage buckets: `public-reports`、`private-inputs`、`private-artifacts`

## 3. 前端读取

前端配置在：

```text
frontend/factor-lab-dashboard/config.js
pages/factor-lab-dashboard/config.js
```

当前配置：

```js
window.FACTOR_LAB_SUPABASE_URL = "https://rebyrzrvnfbwvmbjvhzj.supabase.co";
window.FACTOR_LAB_SUPABASE_ANON_KEY = "sb_publishable_ZHAM5wQWZh_Wng4TaL-fDg_XlFBcB6j";
window.FACTOR_LAB_SUPABASE_FACTOR_TABLE = "public_dashboard_factors";
```

publishable / anon key 可以放前端，但必须配合 RLS。不要把 `service_role` key、数据库密码、对象存储私有签名密钥放进前端。

## 4. 后端写入边界

后端以后只写公开展示结果到：

```text
public_dashboard_factors
public_dashboard_tasks
public_dashboard_metrics
public_dashboard_reports
```

原始研报、代码、实验数据、parquet、完整 artifacts 不直接塞表里。大文件放：

```text
private-inputs
private-artifacts
public-reports
```

其中 `public-reports` 只放可以公开展示的报告摘要或脱敏报告。

## 5. 费用判断

当前框架只包含表结构和少量 JSON/指标行，体量很小。真正占用 Supabase 空间的是：

- PDF / 研报附件
- parquet 因子值大表
- 长历史指标明细
- 大量回测曲线逐日数据

过渡阶段建议只同步审核后的摘要、指标和公开报告链接，不同步全量原始产物。
