-- zoo_factor_dictionary: 因子字典（表达式 + 解释）归档表
-- 来源: runtime/factor_db_zoo_extract.json (GTJA191/JQ110/TDXGS/ALPHA158/ALPHA360/ALPHA101)
-- 面板不展示表达式，只读有效信息；本表用于归档与审计。
create table if not exists public.zoo_factor_dictionary (
  id uuid primary key default gen_random_uuid(),
  library text not null,
  factor_name text not null,
  expression text not null default '',
  comments text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint zoo_factor_dictionary_lib_factor_key unique (library, factor_name)
);

alter table public.zoo_factor_dictionary enable row level security;

-- anon / authenticated 只读
drop policy if exists "zoo_factor_dictionary_select" on public.zoo_factor_dictionary;
create policy "zoo_factor_dictionary_select"
  on public.zoo_factor_dictionary
  for select
  to anon, authenticated
  using (true);

-- service_role 绕过 RLS，可写入（PostgREST 侧无需额外策略）

-- 写入时刷新 updated_at
create or replace function public.zoo_factor_dictionary_touch_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists zoo_factor_dictionary_touch on public.zoo_factor_dictionary;
create trigger zoo_factor_dictionary_touch
  before update on public.zoo_factor_dictionary
  for each row
  execute function public.zoo_factor_dictionary_touch_updated_at();
