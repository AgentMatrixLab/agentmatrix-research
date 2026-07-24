-- Factor Lab dashboard metrics for Alpha101 / WorldQuant_alpha013.
--
-- Run this in Supabase SQL Editor for the target project.
-- It creates the public read dashboard table if missing, then upserts the
-- project-computed IC/IR metrics. The raw table column "value" is the factor
-- value, not IC. IC is computed by Factor Lab from factor values and
-- forward_return_1d using research_core.factor_lab.evaluation.

create extension if not exists pgcrypto;

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

alter table public.public_dashboard_factors enable row level security;

drop policy if exists "public read dashboard factors" on public.public_dashboard_factors;
create policy "public read dashboard factors"
  on public.public_dashboard_factors for select
  to anon, authenticated
  using (true);

grant usage on schema public to anon, authenticated;
grant select on public.public_dashboard_factors to anon, authenticated;

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
  truth_exact_match_ratio,
  truth_max_abs_error,
  latest_task_id,
  latest_checked_at,
  payload
) values (
  'WQ101:alpha13',
  'WorldQuant_alpha013',
  'alpha101',
  'WQ101',
  '量价因子',
  'passed',
  'passed',
  'not_compared',
  'passed',
  0.9833333333333333,
  0.024431372863727593,
  0.09594360253180614,
  0.007408810240204257,
  null,
  null,
  'wq101-real-a516f9d705',
  '2026-07-14T01:45:27.479106Z',
  '{
    "id": "WQ101:alpha13",
    "factor_id": "WQ101:alpha13",
    "factor_name": "WorldQuant_alpha013",
    "raw_factor_name": "alpha13",
    "display_name": "WorldQuant Alpha013",
    "library": "WQ101",
    "raw_library": "Alpha101",
    "factor_family": "alpha101",
    "category": "量价因子",
    "subcategory": "技术指标因子",
    "market": "ashare",
    "universe": "A股",
    "data_source": "supabase_truth_values + project_evaluation",
    "source": "project_hardcode_evaluation",
    "source_id": "runtime/factor_lab/factor_detail_cache/WQ101_alpha13.json",
    "source_document": "WorldQuant 101 Formulaic Alphas",
    "implementation_status": "computed",
    "proof_status": "passed",
    "truth_status": "not_compared",
    "overall_status": "passed",
    "coverage_ratio": 0.9833333333333333,
    "rank_ic_mean": 0.024431372863727593,
    "rank_ic_ir": 0.09594360253180614,
    "pearson_ic_mean": 0.01850775276631223,
    "long_short_mean": 0.007408810240204257,
    "reuse_recommendation": "待确认",
    "latest_job_id": "wq101-real-a516f9d705",
    "latest_checked_at": "2026-07-14T01:45:27.479106Z",
    "dataset": {
      "panel_rows": 4800,
      "factor_rows": 4800,
      "analysis_rows": 4700,
      "symbols": 20,
      "dates": 440,
      "start_date": "2020-01-02",
      "end_date": "2023-06-06",
      "groups": 10
    },
    "truth_dataset": {
      "source_table": "factor_truth_values",
      "source_raw_table": "Alpha101因子13 part1",
      "source_version": "v1",
      "row_count": 182805,
      "symbol_count": 99,
      "start_date": "2016-01-04",
      "end_date": "2026-07-06"
    },
    "metadata": {
      "metric_definition": "rank_ic_mean/rank_ic_ir/long_short_mean are computed from factor values and forward_return_1d, not read from the raw value column.",
      "raw_value_column_meaning": "per-symbol per-date factor truth value",
      "evaluation_module": "research_core.factor_lab.evaluation",
      "evaluation_artifact": "runtime/factor_lab/factor_detail_cache/WQ101_alpha13.json"
    }
  }'::jsonb
)
on conflict (factor_id) do update set
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
  truth_exact_match_ratio = excluded.truth_exact_match_ratio,
  truth_max_abs_error = excluded.truth_max_abs_error,
  latest_task_id = excluded.latest_task_id,
  latest_checked_at = excluded.latest_checked_at,
  payload = excluded.payload,
  updated_at = now();

notify pgrst, 'reload schema';

select
  factor_id,
  factor_name,
  coverage_ratio,
  rank_ic_mean,
  rank_ic_ir,
  long_short_mean,
  latest_checked_at
from public.public_dashboard_factors
where factor_id = 'WQ101:alpha13';
