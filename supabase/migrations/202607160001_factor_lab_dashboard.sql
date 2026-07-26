-- Factor Lab cloud display framework.
-- This migration stores only metadata and public dashboard rows in Postgres.
-- Large PDFs, parquet outputs, and private artifacts should go to Storage
-- buckets or external object storage, not into table columns.

create extension if not exists pgcrypto;

create table if not exists public.factor_registry (
  factor_family text primary key,
  truth_required boolean not null,
  tolerance numeric,
  min_overlap_ratio numeric,
  pass_exact_match_ratio numeric,
  promotion_policy text not null check (promotion_policy in ('auto', 'human_confirm')),
  decay_policy jsonb not null default '{}'::jsonb,
  description text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.tasks (
  id uuid primary key default gen_random_uuid(),
  task_id text not null unique,
  task_type text not null,
  factor_family text,
  status text not null default 'submitted',
  current_gate text,
  criteria jsonb not null default '{}'::jsonb,
  criteria_sha256 text,
  request_payload jsonb not null default '{}'::jsonb,
  status_payload jsonb not null default '{}'::jsonb,
  submitted_by text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.task_files (
  id uuid primary key default gen_random_uuid(),
  task_id text not null references public.tasks(task_id) on delete cascade,
  file_role text not null,
  file_name text not null,
  bucket_name text not null default 'private-inputs',
  object_path text not null,
  content_type text,
  byte_size bigint,
  sha256 text,
  created_at timestamptz not null default now()
);

create table if not exists public.public_dashboard_tasks (
  id uuid primary key default gen_random_uuid(),
  task_id text not null unique,
  task_type text not null,
  title text not null,
  status text not null,
  current_gate text,
  summary text,
  payload jsonb not null default '{}'::jsonb,
  latest_checked_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.public_dashboard_factors (
  id uuid primary key default gen_random_uuid(),
  factor_id text not null unique,
  factor_name text not null,
  factor_family text,
  library text,
  category text,
  status text not null default 'registered',
  proof_status text,
  truth_status text,
  overall_status text,
  coverage_ratio numeric,
  rank_ic_mean numeric,
  rank_ic_ir numeric,
  long_short_mean numeric,
  truth_exact_match_ratio numeric,
  truth_max_abs_error numeric,
  latest_task_id text,
  latest_checked_at timestamptz,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.public_dashboard_metrics (
  id uuid primary key default gen_random_uuid(),
  entity_type text not null check (entity_type in ('factor', 'strategy', 'task')),
  entity_id text not null,
  metric_date date,
  metrics jsonb not null default '{}'::jsonb,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (entity_type, entity_id, metric_date)
);

create table if not exists public.public_dashboard_reports (
  id uuid primary key default gen_random_uuid(),
  report_id text not null unique,
  entity_type text not null check (entity_type in ('factor', 'strategy', 'task')),
  entity_id text not null,
  title text not null,
  report_kind text not null,
  bucket_name text not null default 'public-reports',
  object_path text,
  summary text,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.promotion_logs (
  id uuid primary key default gen_random_uuid(),
  task_id text not null,
  entity_type text not null check (entity_type in ('factor', 'strategy')),
  entity_id text not null,
  decision text not null,
  decision_payload jsonb not null default '{}'::jsonb,
  promoted_by text,
  created_at timestamptz not null default now()
);

alter table public.factor_registry enable row level security;
alter table public.tasks enable row level security;
alter table public.task_files enable row level security;
alter table public.public_dashboard_tasks enable row level security;
alter table public.public_dashboard_factors enable row level security;
alter table public.public_dashboard_metrics enable row level security;
alter table public.public_dashboard_reports enable row level security;
alter table public.promotion_logs enable row level security;

drop policy if exists "public read dashboard tasks" on public.public_dashboard_tasks;
drop policy if exists "public read dashboard factors" on public.public_dashboard_factors;
drop policy if exists "public read dashboard metrics" on public.public_dashboard_metrics;
drop policy if exists "public read dashboard reports" on public.public_dashboard_reports;

create policy "public read dashboard tasks"
  on public.public_dashboard_tasks for select
  to anon, authenticated
  using (true);

create policy "public read dashboard factors"
  on public.public_dashboard_factors for select
  to anon, authenticated
  using (true);

create policy "public read dashboard metrics"
  on public.public_dashboard_metrics for select
  to anon, authenticated
  using (true);

create policy "public read dashboard reports"
  on public.public_dashboard_reports for select
  to anon, authenticated
  using (true);

grant usage on schema public to anon, authenticated;
grant select on public.public_dashboard_tasks to anon, authenticated;
grant select on public.public_dashboard_factors to anon, authenticated;
grant select on public.public_dashboard_metrics to anon, authenticated;
grant select on public.public_dashboard_reports to anon, authenticated;

insert into public.factor_registry (
  factor_family,
  truth_required,
  tolerance,
  min_overlap_ratio,
  pass_exact_match_ratio,
  promotion_policy,
  decay_policy,
  description
) values
  ('alpha101', true, 1e-8, 0.90, 0.99, 'auto', '{"min_rolling_ic": 0.02, "review_window": "250d"}', 'WorldQuant 101 / Alpha101 factor family'),
  ('wq101', true, 1e-8, 0.90, 0.99, 'auto', '{"min_rolling_ic": 0.02, "review_window": "250d"}', 'WorldQuant 101 normalized alias'),
  ('gtja191', true, 1e-8, 0.90, 0.99, 'human_confirm', '{"min_rolling_ic": 0.02, "review_window": "250d"}', 'GTJA 191 factor family'),
  ('exploratory', false, null, null, null, 'auto', '{}', 'Exploratory custom factors without external truth panel')
on conflict (factor_family) do update set
  truth_required = excluded.truth_required,
  tolerance = excluded.tolerance,
  min_overlap_ratio = excluded.min_overlap_ratio,
  pass_exact_match_ratio = excluded.pass_exact_match_ratio,
  promotion_policy = excluded.promotion_policy,
  decay_policy = excluded.decay_policy,
  description = excluded.description,
  updated_at = now();

insert into storage.buckets (id, name, public)
values
  ('public-reports', 'public-reports', true),
  ('private-inputs', 'private-inputs', false),
  ('private-artifacts', 'private-artifacts', false)
on conflict (id) do update set
  public = excluded.public;

drop policy if exists "public read public reports bucket" on storage.objects;

create policy "public read public reports bucket"
  on storage.objects for select
  to anon, authenticated
  using (bucket_id = 'public-reports');
