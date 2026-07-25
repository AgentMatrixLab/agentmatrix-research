-- Factor Lab unified Supabase entry V1.
--
-- Purpose:
--   1. Everyone writes factor data into the same staging tables.
--   2. Backend / Agent normalizes staging rows into canonical tables.
--   3. GitHub Pages reads only public_dashboard_* objects.
--
-- This script is idempotent. Run it in Supabase SQL Editor as a project owner.

create extension if not exists pgcrypto;

create table if not exists public.factor_import_batches (
  batch_id uuid primary key default gen_random_uuid(),
  entry_type text not null check (
    entry_type in (
      'truth_compare',
      'research_reproduction',
      'manual_metric',
      'legacy_table_import'
    )
  ),
  factor_family text not null,
  factor_name text not null,
  library text,
  market text not null default 'A股',
  source_name text not null,
  source_version text not null default 'v1',
  source_uri text,
  submitted_by text,
  status text not null default 'staged' check (
    status in ('staged', 'normalizing', 'normalized', 'published', 'failed')
  ),
  row_count integer not null default 0,
  error_message text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.factor_values_staging (
  id bigserial primary key,
  batch_id uuid not null references public.factor_import_batches(batch_id) on delete cascade,
  factor_family text not null,
  factor_name text not null,
  symbol text not null,
  trade_date date not null,
  value double precision not null,
  value_type text not null default 'submitted' check (
    value_type in ('truth', 'submitted', 'reproduced', 'research')
  ),
  source_version text not null default 'v1',
  raw_payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists factor_values_staging_batch_idx
  on public.factor_values_staging(batch_id);

create index if not exists factor_values_staging_lookup_idx
  on public.factor_values_staging(factor_family, factor_name, value_type, trade_date, symbol);

create table if not exists public.factor_metric_staging (
  id bigserial primary key,
  batch_id uuid not null references public.factor_import_batches(batch_id) on delete cascade,
  factor_family text not null,
  factor_name text not null,
  library text,
  category text,
  market text not null default 'A股',
  status text not null default 'candidate',
  proof_status text,
  truth_status text,
  overall_status text,
  coverage_ratio numeric,
  rank_ic_mean numeric,
  rank_ic_ir numeric,
  ic_mean numeric,
  ic_ir numeric,
  long_short_mean numeric,
  long_short_ir numeric,
  turnover numeric,
  start_date date,
  end_date date,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists factor_metric_staging_batch_idx
  on public.factor_metric_staging(batch_id);

create table if not exists public.factor_values (
  id bigserial primary key,
  factor_id text not null,
  factor_family text not null,
  factor_name text not null,
  symbol text not null,
  trade_date date not null,
  value double precision not null,
  value_type text not null check (
    value_type in ('truth', 'submitted', 'reproduced', 'research')
  ),
  source_batch_id uuid references public.factor_import_batches(batch_id) on delete set null,
  source_name text not null,
  source_version text not null default 'v1',
  source_row_hash text not null,
  metadata jsonb not null default '{}'::jsonb,
  imported_at timestamptz not null default now()
);

create unique index if not exists factor_values_unique_row
  on public.factor_values(
    factor_family,
    factor_name,
    value_type,
    symbol,
    trade_date,
    source_version
  );

create index if not exists factor_values_lookup_idx
  on public.factor_values(factor_family, factor_name, value_type, trade_date, symbol);

-- Compatibility table used by the current Alpha101 truth-value work.
create table if not exists public.factor_truth_values (
  id bigserial primary key,
  factor_family text not null,
  factor_name text not null,
  symbol text not null,
  trade_date date not null,
  truth_value double precision not null,
  source_table text not null,
  source_version text not null default 'v1',
  source_row_hash text not null,
  imported_at timestamptz not null default now(),
  metadata jsonb not null default '{}'::jsonb
);

create unique index if not exists factor_truth_values_unique_row
  on public.factor_truth_values(
    factor_family,
    factor_name,
    symbol,
    trade_date,
    source_version
  );

create index if not exists factor_truth_values_lookup_idx
  on public.factor_truth_values(factor_family, factor_name, trade_date, symbol);

create table if not exists public.factor_metrics (
  id bigserial primary key,
  factor_id text not null,
  factor_family text not null,
  factor_name text not null,
  library text,
  category text,
  market text not null default 'A股',
  status text not null default 'candidate',
  proof_status text,
  truth_status text,
  overall_status text,
  coverage_ratio numeric,
  rank_ic_mean numeric,
  rank_ic_ir numeric,
  ic_mean numeric,
  ic_ir numeric,
  long_short_mean numeric,
  long_short_ir numeric,
  turnover numeric,
  start_date date,
  end_date date,
  source_batch_id uuid references public.factor_import_batches(batch_id) on delete set null,
  source_version text not null default 'v1',
  latest_checked_at timestamptz not null default now(),
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists factor_metrics_unique_version
  on public.factor_metrics(factor_family, factor_name, source_version);

create index if not exists factor_metrics_dashboard_idx
  on public.factor_metrics(factor_family, factor_name, latest_checked_at desc);

-- Existing dashboard table. Kept as a table because the current frontend already reads it.
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

create or replace view public.factor_values_summary as
select
  factor_family,
  factor_name,
  value_type,
  source_version,
  count(*) as row_count,
  count(distinct symbol) as symbol_count,
  min(trade_date) as start_date,
  max(trade_date) as end_date,
  min(value) as min_value,
  max(value) as max_value,
  avg(value) as avg_value,
  max(imported_at) as latest_imported_at
from public.factor_values
group by factor_family, factor_name, value_type, source_version;

create or replace view public.factor_truth_values_summary as
select
  factor_family,
  factor_name,
  source_version,
  count(*) as row_count,
  count(distinct symbol) as symbol_count,
  min(trade_date) as start_date,
  max(trade_date) as end_date,
  min(truth_value) as min_truth_value,
  max(truth_value) as max_truth_value,
  avg(truth_value) as avg_truth_value,
  max(imported_at) as latest_imported_at
from public.factor_truth_values
group by factor_family, factor_name, source_version;

create or replace view public.public_dashboard_factor_values_summary as
select
  factor_family,
  factor_name,
  value_type,
  source_version,
  row_count,
  symbol_count,
  start_date,
  end_date,
  latest_imported_at
from public.factor_values_summary;

create or replace view public.public_dashboard_factor_metrics as
select
  factor_id,
  factor_family,
  factor_name,
  library,
  category,
  market,
  status,
  proof_status,
  truth_status,
  overall_status,
  coverage_ratio,
  rank_ic_mean,
  rank_ic_ir,
  ic_mean,
  ic_ir,
  long_short_mean,
  long_short_ir,
  turnover,
  start_date,
  end_date,
  source_version,
  latest_checked_at,
  metadata
from public.factor_metrics;

create or replace function public.normalize_factor_import_batch(
  p_batch_id uuid,
  p_publish boolean default true
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_batch public.factor_import_batches%rowtype;
  v_value_rows integer := 0;
  v_metric_rows integer := 0;
begin
  select *
    into v_batch
  from public.factor_import_batches
  where batch_id = p_batch_id
  for update;

  if not found then
    raise exception 'Unknown batch_id: %', p_batch_id;
  end if;

  update public.factor_import_batches
    set status = 'normalizing',
        updated_at = now(),
        error_message = null
  where batch_id = p_batch_id;

  insert into public.factor_values (
    factor_id,
    factor_family,
    factor_name,
    symbol,
    trade_date,
    value,
    value_type,
    source_batch_id,
    source_name,
    source_version,
    source_row_hash,
    metadata
  )
  select
    lower(s.factor_family) || ':' || s.factor_name as factor_id,
    lower(s.factor_family) as factor_family,
    s.factor_name,
    trim(s.symbol) as symbol,
    s.trade_date,
    s.value,
    s.value_type,
    s.batch_id,
    v_batch.source_name,
    coalesce(nullif(s.source_version, ''), v_batch.source_version, 'v1') as source_version,
    md5(concat_ws(
      '|',
      lower(s.factor_family),
      s.factor_name,
      s.value_type,
      trim(s.symbol),
      s.trade_date::text,
      s.value::text,
      coalesce(nullif(s.source_version, ''), v_batch.source_version, 'v1')
    )) as source_row_hash,
    s.raw_payload || jsonb_build_object(
      'batch_id', s.batch_id,
      'entry_type', v_batch.entry_type,
      'source_name', v_batch.source_name
    ) as metadata
  from public.factor_values_staging s
  where s.batch_id = p_batch_id
  on conflict (
    factor_family,
    factor_name,
    value_type,
    symbol,
    trade_date,
    source_version
  )
  do update set
    value = excluded.value,
    source_batch_id = excluded.source_batch_id,
    source_name = excluded.source_name,
    source_row_hash = excluded.source_row_hash,
    metadata = excluded.metadata,
    imported_at = now();

  get diagnostics v_value_rows = row_count;

  insert into public.factor_truth_values (
    factor_family,
    factor_name,
    symbol,
    trade_date,
    truth_value,
    source_table,
    source_version,
    source_row_hash,
    metadata
  )
  select
    lower(s.factor_family),
    s.factor_name,
    trim(s.symbol),
    s.trade_date,
    s.value,
    v_batch.source_name,
    coalesce(nullif(s.source_version, ''), v_batch.source_version, 'v1'),
    md5(concat_ws(
      '|',
      lower(s.factor_family),
      s.factor_name,
      trim(s.symbol),
      s.trade_date::text,
      s.value::text,
      coalesce(nullif(s.source_version, ''), v_batch.source_version, 'v1')
    )),
    s.raw_payload || jsonb_build_object(
      'batch_id', s.batch_id,
      'entry_type', v_batch.entry_type,
      'source_name', v_batch.source_name
    )
  from public.factor_values_staging s
  where s.batch_id = p_batch_id
    and s.value_type = 'truth'
  on conflict (
    factor_family,
    factor_name,
    symbol,
    trade_date,
    source_version
  )
  do update set
    truth_value = excluded.truth_value,
    source_table = excluded.source_table,
    source_row_hash = excluded.source_row_hash,
    metadata = excluded.metadata,
    imported_at = now();

  insert into public.factor_metrics (
    factor_id,
    factor_family,
    factor_name,
    library,
    category,
    market,
    status,
    proof_status,
    truth_status,
    overall_status,
    coverage_ratio,
    rank_ic_mean,
    rank_ic_ir,
    ic_mean,
    ic_ir,
    long_short_mean,
    long_short_ir,
    turnover,
    start_date,
    end_date,
    source_batch_id,
    source_version,
    latest_checked_at,
    metadata
  )
  select
    lower(m.factor_family) || ':' || m.factor_name,
    lower(m.factor_family),
    m.factor_name,
    m.library,
    m.category,
    coalesce(m.market, v_batch.market, 'A股'),
    coalesce(nullif(m.status, ''), 'candidate'),
    m.proof_status,
    m.truth_status,
    m.overall_status,
    m.coverage_ratio,
    m.rank_ic_mean,
    m.rank_ic_ir,
    m.ic_mean,
    m.ic_ir,
    m.long_short_mean,
    m.long_short_ir,
    m.turnover,
    m.start_date,
    m.end_date,
    m.batch_id,
    coalesce(v_batch.source_version, 'v1'),
    now(),
    m.metadata || jsonb_build_object(
      'batch_id', m.batch_id,
      'entry_type', v_batch.entry_type,
      'source_name', v_batch.source_name
    )
  from public.factor_metric_staging m
  where m.batch_id = p_batch_id
  on conflict (factor_family, factor_name, source_version)
  do update set
    library = excluded.library,
    category = excluded.category,
    market = excluded.market,
    status = excluded.status,
    proof_status = excluded.proof_status,
    truth_status = excluded.truth_status,
    overall_status = excluded.overall_status,
    coverage_ratio = excluded.coverage_ratio,
    rank_ic_mean = excluded.rank_ic_mean,
    rank_ic_ir = excluded.rank_ic_ir,
    ic_mean = excluded.ic_mean,
    ic_ir = excluded.ic_ir,
    long_short_mean = excluded.long_short_mean,
    long_short_ir = excluded.long_short_ir,
    turnover = excluded.turnover,
    start_date = excluded.start_date,
    end_date = excluded.end_date,
    source_batch_id = excluded.source_batch_id,
    latest_checked_at = now(),
    metadata = excluded.metadata,
    updated_at = now();

  get diagnostics v_metric_rows = row_count;

  if p_publish then
    with s as (
      select *
      from public.factor_values_summary s0
      where s0.factor_family = lower(v_batch.factor_family)
        and s0.factor_name = v_batch.factor_name
        and s0.source_version = v_batch.source_version
      order by
        case s0.value_type when 'truth' then 1 when 'submitted' then 2 when 'reproduced' then 3 else 4 end,
        s0.latest_imported_at desc
      limit 1
    ),
    m as (
      select *
      from public.factor_metrics m0
      where m0.source_batch_id = p_batch_id
         or (
          m0.factor_family = lower(v_batch.factor_family)
          and m0.factor_name = v_batch.factor_name
          and m0.source_version = v_batch.source_version
        )
      order by m0.latest_checked_at desc
      limit 1
    )
    insert into public.public_dashboard_factors (
      factor_id,
      factor_name,
      factor_family,
      library,
      category,
      status,
      proof_status,
      truth_status,
      overall_status,
      coverage_ratio,
      rank_ic_mean,
      rank_ic_ir,
      long_short_mean,
      latest_task_id,
      latest_checked_at,
      payload
    )
    select
      coalesce(m.factor_id, lower(v_batch.factor_family) || ':' || v_batch.factor_name),
      coalesce(m.factor_name, s.factor_name, v_batch.factor_name),
      coalesce(m.factor_family, s.factor_family, lower(v_batch.factor_family)),
      coalesce(m.library, v_batch.library),
      m.category,
      coalesce(m.status, 'candidate'),
      m.proof_status,
      coalesce(m.truth_status, case when s.value_type = 'truth' then 'pending_compare' else 'not_applicable' end),
      coalesce(m.overall_status, m.status, 'candidate'),
      coalesce(m.coverage_ratio, case when s.row_count > 0 then 1.0 else null end),
      m.rank_ic_mean,
      m.rank_ic_ir,
      m.long_short_mean,
      p_batch_id::text,
      coalesce(m.latest_checked_at, s.latest_imported_at, now()),
      coalesce(m.metadata, '{}'::jsonb) || jsonb_build_object(
        'source', 'supabase_unified_entry',
        'entry_type', v_batch.entry_type,
        'source_name', v_batch.source_name,
        'source_version', v_batch.source_version,
        'value_summary', to_jsonb(s)
      )
    from s
    full outer join m on true
    on conflict (factor_id)
    do update set
      factor_name = excluded.factor_name,
      factor_family = excluded.factor_family,
      library = excluded.library,
      category = excluded.category,
      status = excluded.status,
      proof_status = excluded.proof_status,
      truth_status = excluded.truth_status,
      overall_status = excluded.overall_status,
      coverage_ratio = excluded.coverage_ratio,
      rank_ic_mean = excluded.rank_ic_mean,
      rank_ic_ir = excluded.rank_ic_ir,
      long_short_mean = excluded.long_short_mean,
      latest_task_id = excluded.latest_task_id,
      latest_checked_at = excluded.latest_checked_at,
      payload = excluded.payload,
      updated_at = now();
  end if;

  update public.factor_import_batches
    set status = case when p_publish then 'published' else 'normalized' end,
        row_count = (
          select count(*)
          from public.factor_values_staging
          where batch_id = p_batch_id
        ),
        updated_at = now()
  where batch_id = p_batch_id;

  return jsonb_build_object(
    'batch_id', p_batch_id,
    'status', case when p_publish then 'published' else 'normalized' end,
    'value_rows_upserted', v_value_rows,
    'metric_rows_upserted', v_metric_rows,
    'published', p_publish
  );
exception when others then
  update public.factor_import_batches
    set status = 'failed',
        error_message = sqlerrm,
        updated_at = now()
  where batch_id = p_batch_id;
  raise;
end;
$$;

alter table public.factor_import_batches enable row level security;
alter table public.factor_values_staging enable row level security;
alter table public.factor_metric_staging enable row level security;
alter table public.factor_values enable row level security;
alter table public.factor_truth_values enable row level security;
alter table public.factor_metrics enable row level security;
alter table public.public_dashboard_factors enable row level security;

drop policy if exists "authenticated stage import batches" on public.factor_import_batches;
drop policy if exists "authenticated stage factor values" on public.factor_values_staging;
drop policy if exists "authenticated stage factor metrics" on public.factor_metric_staging;
drop policy if exists "authenticated read canonical factor values" on public.factor_values;
drop policy if exists "authenticated read canonical truth values" on public.factor_truth_values;
drop policy if exists "authenticated read canonical factor metrics" on public.factor_metrics;
drop policy if exists "public read dashboard factors" on public.public_dashboard_factors;

create policy "authenticated stage import batches"
  on public.factor_import_batches
  for all
  to authenticated
  using (true)
  with check (true);

create policy "authenticated stage factor values"
  on public.factor_values_staging
  for all
  to authenticated
  using (true)
  with check (true);

create policy "authenticated stage factor metrics"
  on public.factor_metric_staging
  for all
  to authenticated
  using (true)
  with check (true);

create policy "authenticated read canonical factor values"
  on public.factor_values
  for select
  to authenticated
  using (true);

create policy "authenticated read canonical truth values"
  on public.factor_truth_values
  for select
  to authenticated
  using (true);

create policy "authenticated read canonical factor metrics"
  on public.factor_metrics
  for select
  to authenticated
  using (true);

create policy "public read dashboard factors"
  on public.public_dashboard_factors
  for select
  to anon, authenticated
  using (true);

grant usage on schema public to anon, authenticated;

grant select on public.public_dashboard_factors to anon, authenticated;
grant select on public.public_dashboard_factor_values_summary to anon, authenticated;
grant select on public.public_dashboard_factor_metrics to anon, authenticated;
grant select on public.factor_truth_values_summary to anon, authenticated;

grant select, insert, update on public.factor_import_batches to authenticated;
grant select, insert, update, delete on public.factor_values_staging to authenticated;
grant select, insert, update, delete on public.factor_metric_staging to authenticated;
grant select on public.factor_values to authenticated;
grant select on public.factor_truth_values to authenticated;
grant select on public.factor_metrics to authenticated;
grant execute on function public.normalize_factor_import_batch(uuid, boolean) to authenticated;

grant usage, select on sequence public.factor_values_staging_id_seq to authenticated;
grant usage, select on sequence public.factor_metric_staging_id_seq to authenticated;
grant usage, select on sequence public.factor_values_id_seq to authenticated;
grant usage, select on sequence public.factor_truth_values_id_seq to authenticated;
grant usage, select on sequence public.factor_metrics_id_seq to authenticated;
