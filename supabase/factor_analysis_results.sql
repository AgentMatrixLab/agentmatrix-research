-- Factor Lab formal single-factor analysis schema.
--
-- Design:
-- 1) factor_analysis_results stores one lightweight summary row per run.
-- 2) factor_analysis_ic_series stores the IC time series.
-- 3) factor_analysis_group_series stores group and long-short chart series.
--
-- This file is safe to run multiple times. If an older JSON-only
-- factor_analysis_results table already exists, this upgrades it in place.

create extension if not exists pgcrypto;

create table if not exists public.factor_analysis_results (
  id uuid primary key default gen_random_uuid(),
  factor_id text,
  factor_name text not null,
  library text not null,
  factor_family text,
  source_version text default 'v1',
  data_source text,
  config_hash text,
  n_groups integer,
  n_symbols integer,
  n_dates integer,
  dataset jsonb default '{}'::jsonb,
  metrics jsonb default '{}'::jsonb,
  ic_summary jsonb default '{}'::jsonb,
  group_returns_summary jsonb default '{}'::jsonb,
  long_short_summary jsonb default '{}'::jsonb,
  monotonicity jsonb default '{}'::jsonb,
  chart_data jsonb default '{}'::jsonb,
  generated_at timestamptz default now(),
  created_at timestamptz default now(),
  unique (factor_name, library, config_hash)
);

alter table public.factor_analysis_results
  add column if not exists factor_id text,
  add column if not exists factor_family text,
  add column if not exists source_version text default 'v1',
  add column if not exists data_source text,
  add column if not exists config_hash text,
  add column if not exists n_groups integer,
  add column if not exists n_symbols integer,
  add column if not exists n_dates integer,
  add column if not exists dataset jsonb default '{}'::jsonb,
  add column if not exists metrics jsonb default '{}'::jsonb,
  add column if not exists ic_summary jsonb default '{}'::jsonb,
  add column if not exists group_returns_summary jsonb default '{}'::jsonb,
  add column if not exists long_short_summary jsonb default '{}'::jsonb,
  add column if not exists monotonicity jsonb default '{}'::jsonb,
  add column if not exists chart_data jsonb default '{}'::jsonb,
  add column if not exists generated_at timestamptz default now(),
  add column if not exists created_at timestamptz default now();

alter table public.factor_analysis_results
  alter column chart_data drop not null;

create unique index if not exists idx_factor_analysis_results_unique
  on public.factor_analysis_results (factor_name, library, config_hash);

create index if not exists idx_factor_analysis_results_lookup
  on public.factor_analysis_results (factor_name, library, generated_at desc);

create index if not exists idx_factor_analysis_results_factor_id
  on public.factor_analysis_results (factor_id);

create table if not exists public.factor_analysis_ic_series (
  id bigserial primary key,
  factor_name text not null,
  library text not null,
  config_hash text not null,
  trade_date date not null,
  rank_ic double precision,
  pearson_ic double precision,
  n_stocks integer,
  created_at timestamptz default now(),
  unique (factor_name, library, config_hash, trade_date)
);

create index if not exists idx_factor_analysis_ic_lookup
  on public.factor_analysis_ic_series (factor_name, library, config_hash, trade_date);

create table if not exists public.factor_analysis_group_series (
  id bigserial primary key,
  factor_name text not null,
  library text not null,
  config_hash text not null,
  trade_date date not null,
  series_key text not null,
  series_type text not null default 'group',
  group_no integer,
  group_return double precision,
  group_nav double precision,
  created_at timestamptz default now(),
  unique (factor_name, library, config_hash, trade_date, series_key)
);

create index if not exists idx_factor_analysis_group_lookup
  on public.factor_analysis_group_series (factor_name, library, config_hash, trade_date);

create index if not exists idx_factor_analysis_group_series_key
  on public.factor_analysis_group_series (factor_name, library, config_hash, series_key);

alter table public.factor_analysis_results enable row level security;
alter table public.factor_analysis_ic_series enable row level security;
alter table public.factor_analysis_group_series enable row level security;

drop policy if exists "factor_analysis_results_public_read" on public.factor_analysis_results;
create policy "factor_analysis_results_public_read"
  on public.factor_analysis_results
  for select
  to anon
  using (true);

drop policy if exists "factor_analysis_ic_series_public_read" on public.factor_analysis_ic_series;
create policy "factor_analysis_ic_series_public_read"
  on public.factor_analysis_ic_series
  for select
  to anon
  using (true);

drop policy if exists "factor_analysis_group_series_public_read" on public.factor_analysis_group_series;
create policy "factor_analysis_group_series_public_read"
  on public.factor_analysis_group_series
  for select
  to anon
  using (true);

comment on table public.factor_analysis_results is
  'Lightweight per-run single-factor analysis summary. Large chart series are stored in split series tables.';

comment on table public.factor_analysis_ic_series is
  'Rank/Pearson IC time series for Factor Lab detail charts.';

comment on table public.factor_analysis_group_series is
  'Group return and NAV series for Factor Lab stratification and group performance charts.';
