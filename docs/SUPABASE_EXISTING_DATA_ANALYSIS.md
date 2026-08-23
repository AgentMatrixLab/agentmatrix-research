# Supabase Existing Data Analysis

本文档基于从 Supabase 导出的 CSV 快照，分析当前已有表能否接入 Factor Lab / GitHub Pages 前端。

## 1. 文件范围

已分析文件：

```text
agents_rows.csv
analytics_page_views_rows.csv
manual_trigger_order_account_state_rows.csv
manual_trigger_orders_rows.csv
profiles_rows.csv
signal_blacklist_rows.csv
signal_pools_rows.csv
signals_rows.csv
strategy_runtime_config_rows.csv
user_credits_rows.csv
user_subscriptions_rows.csv
```

未包含：

```text
quant_signals_rows.csv
quant_performance_rows.csv
```

所以当前判断以 `signals`、`signal_pools`、`manual_trigger_orders` 这几张表为主。

## 2. 总体结论

这些表不是 Factor Lab 的因子库表，而是一套策略信号 / 订单 / 用户 / 访问日志系统。

适合接前端展示的表：

```text
signals
signal_pools
signal_blacklist
strategy_runtime_config
```

可内部展示、但不建议公开 GitHub Pages 直接展示的表：

```text
manual_trigger_orders
manual_trigger_order_account_state
```

不应进入公开展示的表：

```text
profiles
user_credits
user_subscriptions
analytics_page_views
```

原因：

```text
profiles / user_* 涉及用户身份、邮箱、额度、订阅。
analytics_page_views 涉及 visitor_id、user_id、user_agent。
manual_trigger_order_account_state 可能涉及账户级订单状态。
```

## 3. 表级分析

### 3.1 signals

行数：

```text
1378
```

字段：

```text
id
pool_id
symbol
action
status
source
stock_name_raw
signal_raw
industry
target_position_raw
note
created_at
trade_date
cohort_id
```

分布：

```text
action:
  HOLD 691
  BUY  439
  SELL 248

status:
  ARCHIVED 1294
  ACTIVE   84

source:
  image_signal 1378

pool_id:
  daily_stock_pool   876
  weekly_stock_pool  283
  monthly_etf_pool   219
```

时间范围：

```text
created_at: 2026-06-09 -> 2026-07-22
trade_date: 2026-06-09 -> 2026-07-22
```

判断：

```text
这是最适合接到前端的核心表。
但它是“信号表”，不是“因子表”。
```

建议展示方式：

```text
新建“信号监控 / 策略看板”页面。
展示今日 ACTIVE 信号、BUY/SELL/HOLD 分布、信号池分布、行业分布、交易日期。
```

不建议：

```text
不要硬塞进 public_dashboard_factors。
signals 没有 factor_id、rank_ic_ir、truth_status、proof_status 等因子字段。
```

### 3.2 signal_pools

行数：

```text
4
```

字段：

```text
pool_id
pool_name
rebalance_freq
rebalance_weekday
rebalance_monthday
target_allocation
reserve_symbol
enabled
execution_priority
note
created_at
updated_at
```

信号池：

```text
daily_stock_pool
weekly_stock_pool
monthly_etf_pool
reserve_159552_pool
```

判断：

```text
这是 signals 的配置表。
可以用于前端展示“信号池配置”和 signals 的 pool_name 映射。
```

### 3.3 strategy_runtime_config

行数：

```text
15
```

字段：

```text
id
strategy_name
config_key
config_value
enabled
note
created_at
updated_at
```

分布：

```text
strategy_name: multi_pool_supabase_executor
enabled: 全部 true
```

判断：

```text
这是策略执行参数表。
可以作为内部策略配置展示，不建议在公开页面展示完整 config_value。
```

### 3.4 manual_trigger_orders

行数：

```text
8
```

字段包含：

```text
symbol
side
status
trigger_type
trigger_price
target_cash
target_shares
account_scope
hold_mode
enabled
last_price
submitted_price
submitted_volume
submitted_amount
last_message
triggered_at
filled_at
closed_at
```

状态分布：

```text
WATCHING  4
CANCELLED 3
HOLDING   1
```

判断：

```text
这是人工触发订单表。
更适合内部交易监控，不适合直接放公开 GitHub Pages。
```

如果展示，建议只展示脱敏聚合：

```text
订单状态计数
触发类型计数
最近更新时间
```

不要展示：

```text
target_cash
submitted_amount
account_scope
具体账户状态
```

### 3.5 manual_trigger_order_account_state

行数：

```text
16
```

判断：

```text
账户级订单状态，比 manual_trigger_orders 更敏感。
不建议放公开页面。
```

### 3.6 analytics_page_views

行数：

```text
1345
```

包含：

```text
visitor_id
user_id
user_agent
path
created_at
```

判断：

```text
访问日志，不属于 Factor Lab 或策略信号展示数据。
不建议进入公开面板。
```

### 3.7 profiles / user_credits / user_subscriptions

判断：

```text
用户系统数据，不应放到公开前端。
```

## 4. 和 Factor Lab 的关系

当前 Factor Lab 前端读取：

```text
public_dashboard_factors
```

但这些 CSV 里没有因子库字段：

```text
factor_id
factor_name
library
rank_ic_mean
rank_ic_ir
coverage_ratio
proof_status
truth_status
overall_status
```

因此，不建议把实习生清洗的 signals 数据直接导入：

```text
public_dashboard_factors
```

更合理的做法是新增：

```text
public_dashboard_signals
public_dashboard_signal_pools
```

或者先建只读 view：

```text
public_dashboard_signals
public_dashboard_signal_summary
public_dashboard_signal_pools
```

然后前端新增一个“信号监控 / 策略看板”页面来读这些 view。

## 5. 建议前端展示模块

建议新增侧边栏入口：

```text
信号监控
```

页面分区：

```text
1. 概览指标
   - 总信号数
   - ACTIVE 信号数
   - BUY / SELL / HOLD 数量
   - 最新 trade_date

2. 信号池
   - daily_stock_pool
   - weekly_stock_pool
   - monthly_etf_pool
   - reserve_159552_pool

3. 最新信号列表
   - trade_date
   - symbol
   - action
   - status
   - source
   - industry
   - target_position_raw

4. 黑名单
   - symbol
   - risk_type
   - status

5. 策略配置摘要
   - strategy_name
   - config_key
   - enabled
```

## 6. 建议 SQL View

建议先不改原始表，只创建面向前端的只读 view：

```sql
create or replace view public.public_dashboard_signals as
select
  s.id::text as signal_id,
  s.pool_id,
  p.pool_name,
  p.rebalance_freq,
  s.symbol,
  s.action,
  s.status,
  s.source,
  s.stock_name_raw,
  s.signal_raw,
  s.industry,
  s.target_position_raw,
  s.note,
  s.trade_date,
  s.created_at
from public.signals s
left join public.signal_pools p
  on p.pool_id = s.pool_id;
```

```sql
create or replace view public.public_dashboard_signal_summary as
select
  count(*) as total_signals,
  count(*) filter (where status = 'ACTIVE') as active_signals,
  count(*) filter (where action = 'BUY') as buy_signals,
  count(*) filter (where action = 'SELL') as sell_signals,
  count(*) filter (where action = 'HOLD') as hold_signals,
  max(trade_date) as latest_trade_date,
  max(created_at) as latest_created_at
from public.signals;
```

```sql
create or replace view public.public_dashboard_signal_pools as
select
  p.*,
  count(s.id) as signal_count,
  count(s.id) filter (where s.status = 'ACTIVE') as active_signal_count
from public.signal_pools p
left join public.signals s
  on s.pool_id = p.pool_id
group by
  p.pool_id,
  p.pool_name,
  p.rebalance_freq,
  p.rebalance_weekday,
  p.rebalance_monthday,
  p.target_allocation,
  p.reserve_symbol,
  p.enabled,
  p.execution_priority,
  p.note,
  p.created_at,
  p.updated_at;
```

## 7. 权限建议

这些 view 可以给前端只读：

```sql
grant select on public.public_dashboard_signals to anon, authenticated;
grant select on public.public_dashboard_signal_summary to anon, authenticated;
grant select on public.public_dashboard_signal_pools to anon, authenticated;
```

如果 Supabase 对 view + RLS 有额外限制，建议改成物化表或普通表，由后端定时同步。

## 8. 下一步

推荐下一步：

```text
1. 在 Supabase 创建 public_dashboard_signals 相关 view。
2. 前端新增“信号监控”页面。
3. 不把 signals 混入 Factor Lab 因子库页面。
4. 保持 Factor Lab 因子库页面继续读 public_dashboard_factors。
```
