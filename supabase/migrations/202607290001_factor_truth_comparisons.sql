-- 任务一 · 真值对照结果记录表（幂等，可重复运行）
create table if not exists public.factor_truth_comparisons (
  id uuid primary key default gen_random_uuid(),
  run_id text not null unique,
  factor_family text not null,
  factor_name text not null,
  task_id text,
  truth_source text,
  uploaded_rows integer,
  truth_rows integer,
  overlap_ratio numeric,
  exact_match_ratio numeric,
  max_abs_error double precision,
  mean_abs_error double precision,
  status text not null check (status in ('passed', 'failed', 'not_comparable')),
  decision text not null,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists factor_truth_comparisons_lookup_idx
  on public.factor_truth_comparisons (factor_family, factor_name, created_at desc);

alter table public.factor_truth_comparisons enable row level security;

create or replace view public.public_dashboard_truth_comparisons as
select run_id, factor_family, factor_name, task_id,
       uploaded_rows, truth_rows, overlap_ratio, exact_match_ratio,
       max_abs_error, mean_abs_error, status, decision, created_at
from public.factor_truth_comparisons
order by created_at desc;

grant select on public.public_dashboard_truth_comparisons to anon, authenticated;