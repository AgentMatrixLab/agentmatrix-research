-- factor_lifecycle: FACTOR_LIFECYCLE.md v2.0 的云端承载
-- 1) zoo_factor_dictionary 补生命周期字段（状态机 / source_class / OOS 计数）
-- 2) factor_hypothesis 假设登记表（闸门1 四项 + 方向锁定 + 预注册切分）
-- 3) factor_lifecycle_events 证据链账本（append-only，无证据的状态变更视为非法）

-- ---------------------------------------------------------------------------
-- 1. 因子字典补生命周期字段
-- ---------------------------------------------------------------------------

alter table public.zoo_factor_dictionary
  add column if not exists lifecycle_state text not null default '1_implemented',
  add column if not exists source_class text check (source_class in ('novel', 'replication')),
  add column if not exists expected_direction int check (expected_direction in (1, -1)),
  add column if not exists oos_access_count int not null default 0,
  add column if not exists trust_tier text check (trust_tier in ('S', 'A', 'B', 'C', 'D'));

comment on column public.zoo_factor_dictionary.lifecycle_state is
  'FACTOR_LIFECYCLE.md v2.0 状态机：0_conceived..9_rejected，默认 1_implemented（mock 通过）';
comment on column public.zoo_factor_dictionary.source_class is
  'novel=挖掘机原创（预注册 OOS）/ replication=复现已发表（发表后 OOS）';
comment on column public.zoo_factor_dictionary.oos_access_count is
  '封存 holdout 访问计数，上限 3 次，超限自动 9_rejected';

-- ---------------------------------------------------------------------------
-- 2. 假设登记表（闸门1）
-- ---------------------------------------------------------------------------

create table if not exists public.factor_hypothesis (
  id uuid primary key default gen_random_uuid(),
  factor_id text not null unique,
  statement text not null,            -- ① 假设陈述
  source_ref text not null,           -- ② 出处：DOI / 研报页码 / prompt+模型版本+温度
  expected_direction int not null check (expected_direction in (1, -1)),  -- ③ 方向，入队锁死
  econ_logic text not null,           -- ④ 经济学逻辑一句话
  source_class text not null check (source_class in ('novel', 'replication')),
  prereg_split_date date,             -- novel 类必填：实现前锁定的 IS/OOS 切分点
  status text not null default 'conceived'
    check (status in ('conceived', 'rejected')),
  created_at timestamptz not null default now()
);

alter table public.factor_hypothesis enable row level security;

drop policy if exists "factor_hypothesis_select" on public.factor_hypothesis;
create policy "factor_hypothesis_select"
  on public.factor_hypothesis
  for select
  to anon, authenticated
  using (true);

-- ---------------------------------------------------------------------------
-- 3. 证据链账本（append-only）
-- ---------------------------------------------------------------------------

create table if not exists public.factor_lifecycle_events (
  id uuid primary key default gen_random_uuid(),
  factor_id text not null,
  from_state text not null,
  to_state text not null,
  gate text not null,                 -- 例：G2-8 / G4-15 / decay
  evidence jsonb not null,            -- 数值、数据源、窗口、commit、runner 版本
  approved_by text not null,          -- auto:agent / human:姓名（闸门15 须署真名）
  oos_access_count int,               -- 若本次开封了封存 holdout 则记录累计次数
  created_at timestamptz not null default now(),
  -- 只允许插入与查询，禁止更新删除（append-only 由触发器强制）
  constraint factor_lifecycle_events_transition_check check (
    (from_state, to_state) in (
      ('inspiration_pool', '0_conceived'),
      ('inspiration_pool', '9_rejected'),
      ('0_conceived', '1_implemented'),
      ('1_implemented', '2_validated'),
      ('2_validated', '3_strategy_candidate'),
      ('3_strategy_candidate', '4_live_ready'),
      ('4_live_ready', '6_published'),
      ('6_published', '5_suspended'),
      ('5_suspended', '6_published'),
      ('5_suspended', '8_retired'),
      ('6_published', '7_deprecated'),
      ('7_deprecated', '8_retired')
    ) or to_state = '9_rejected'
  )
);

alter table public.factor_lifecycle_events enable row level security;

drop policy if exists "factor_lifecycle_events_select" on public.factor_lifecycle_events;
create policy "factor_lifecycle_events_select"
  on public.factor_lifecycle_events
  for select
  to anon, authenticated
  using (true);

-- append-only：拒绝 UPDATE / DELETE（service_role 也受触发器约束）
create or replace function public.factor_lifecycle_events_block_mutation()
returns trigger
language plpgsql
as $$
begin
  raise exception 'factor_lifecycle_events is append-only (FACTOR_LIFECYCLE.md v2.0 §2)';
end;
$$;

drop trigger if exists factor_lifecycle_events_block_update on public.factor_lifecycle_events;
create trigger factor_lifecycle_events_block_update
  before update on public.factor_lifecycle_events
  for each row
  execute function public.factor_lifecycle_events_block_mutation();

drop trigger if exists factor_lifecycle_events_block_delete on public.factor_lifecycle_events;
create trigger factor_lifecycle_events_block_delete
  before delete on public.factor_lifecycle_events
  for each row
  execute function public.factor_lifecycle_events_block_mutation();
