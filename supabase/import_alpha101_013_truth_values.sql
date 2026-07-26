-- Normalize the existing Alpha101 factor-13 table into one canonical truth table.
--
-- Run this in Supabase SQL Editor while connected to the project that contains:
--   public."Alpha101因子13 part1"
--
-- This script is idempotent: it can be run multiple times without duplicating rows.

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
  imported_at timestamp with time zone not null default now(),
  metadata jsonb not null default '{}'::jsonb
);

alter table public.factor_truth_values
  add column if not exists factor_family text,
  add column if not exists factor_name text,
  add column if not exists symbol text,
  add column if not exists trade_date date,
  add column if not exists truth_value double precision,
  add column if not exists source_table text,
  add column if not exists source_version text default 'v1',
  add column if not exists source_row_hash text,
  add column if not exists imported_at timestamp with time zone default now(),
  add column if not exists metadata jsonb default '{}'::jsonb;

create unique index if not exists factor_truth_values_unique_row
  on public.factor_truth_values (
    factor_family,
    factor_name,
    symbol,
    trade_date,
    source_version
  );

create index if not exists factor_truth_values_lookup_idx
  on public.factor_truth_values (factor_family, factor_name, trade_date, symbol);

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
  'alpha101' as factor_family,
  trim(src.factor) as factor_name,
  trim(src.order_book_id) as symbol,
  to_date(trim(src.date), 'YYYY-MM-DD') as trade_date,
  src.value::double precision as truth_value,
  'Alpha101因子13 part1' as source_table,
  'v1' as source_version,
  md5(
    concat_ws(
      '|',
      'alpha101',
      trim(src.factor),
      trim(src.order_book_id),
      trim(src.date),
      src.value::text
    )
  ) as source_row_hash,
  jsonb_build_object(
    'import_note', 'normalized from public."Alpha101因子13 part1"',
    'original_factor', src.factor
  ) as metadata
from public."Alpha101因子13 part1" src
where src.order_book_id is not null
  and src.date is not null
  and src.value is not null
  and src.factor is not null
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

-- Keep raw truth values backend-facing by default.
-- If the team decides this summary can be public, grant only the summary view:
grant select on public.factor_truth_values_summary to anon, authenticated;

select *
from public.factor_truth_values_summary
where factor_family = 'alpha101'
  and factor_name = 'WorldQuant_alpha013';
