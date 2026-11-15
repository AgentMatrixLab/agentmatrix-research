-- Private owner-isolated workflow. No existing research or public tables are changed.
begin;

create table if not exists public.pf_members (
  user_id uuid primary key references auth.users(id),
  role text not null check (role in ('collaborator','admin')),
  active boolean not null default true
);

create or replace function public.pf_member() returns boolean
language sql stable security definer set search_path = '' as $$
  select exists(select 1 from public.pf_members m where m.user_id=auth.uid() and m.active
    and (m.role<>'admin' or auth.jwt()->>'aal'='aal2'))
$$;

create or replace function public.pf_admin() returns boolean
language sql stable security definer set search_path = '' as $$
  select exists(select 1 from public.pf_members m where m.user_id=auth.uid()
    and m.active and m.role='admin' and auth.jwt()->>'aal'='aal2')
$$;

create or replace function public.pf_access(p_owner uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select public.pf_member() and (p_owner=auth.uid() or public.pf_admin())
$$;

create table if not exists public.pf_submissions (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id),
  factor_id text not null,
  version integer not null check (version>0),
  title text not null,
  formula text not null,
  license text not null,
  code_hash text not null default '',
  config_hash text not null default '',
  data_hash text not null default '',
  metrics jsonb not null default '{}'::jsonb,
  blockers jsonb not null default '[]'::jsonb check (jsonb_typeof(blockers)='array'),
  verification_stage text not null check (verification_stage in ('implemented','partial_proof','internal_validated')),
  state text not null default 'draft' check (state in ('draft','submitted','under_review','admitted','returned','rejected')),
  reviewer_id uuid references auth.users(id),
  frozen_hash text,
  frozen_manifest jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  submitted_at timestamptz,
  unique(owner_id,factor_id,version)
);
create index if not exists pf_owner on public.pf_submissions(owner_id,created_at);
create index if not exists pf_state on public.pf_submissions(state);

create table if not exists public.pf_files (
  id uuid primary key default gen_random_uuid(),
  submission_id uuid not null references public.pf_submissions(id),
  name text not null,
  object_path text not null unique,
  size_bytes bigint not null check (size_bytes between 1 and 26214400),
  sha256 text not null check (sha256 ~ '^[0-9a-f]{64}$'),
  status text not null default 'reserved' check (status in ('reserved','uploaded','manually_checked')),
  checked_by uuid references auth.users(id),
  checked_at timestamptz,
  check_note text,
  unique(submission_id,name)
);
create table if not exists public.pf_reviews (
  id uuid primary key default gen_random_uuid(),
  submission_id uuid not null references public.pf_submissions(id),
  reviewer_id uuid not null references auth.users(id),
  decision text not null check (decision in ('admitted','returned','rejected')),
  note text not null,
  attestation jsonb not null,
  created_at timestamptz not null default now()
);
create table if not exists public.pf_audit (
  id bigint generated always as identity primary key,
  submission_id uuid not null references public.pf_submissions(id),
  actor_id uuid not null references auth.users(id),
  action text not null,
  created_at timestamptz not null default now()
);

create or replace function public.pf_submission_access(p_id uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists(select 1 from public.pf_submissions s where s.id=p_id and public.pf_access(s.owner_id))
$$;

-- Strict guards also protect against OR-combined permissive policies applied by accident.
alter table public.pf_members enable row level security;
alter table public.pf_submissions enable row level security;
alter table public.pf_files enable row level security;
alter table public.pf_reviews enable row level security;
alter table public.pf_audit enable row level security;
revoke all on public.pf_members,public.pf_submissions,public.pf_files,public.pf_reviews,public.pf_audit from public,anon,authenticated;
grant select on public.pf_members,public.pf_submissions,public.pf_files,public.pf_reviews,public.pf_audit to authenticated;
grant all on public.pf_members,public.pf_submissions,public.pf_files,public.pf_reviews,public.pf_audit to service_role;
grant usage,select on sequence public.pf_audit_id_seq to service_role;

do $$
declare t text; predicate text;
begin
  foreach t in array array['pf_members','pf_submissions','pf_files','pf_reviews','pf_audit'] loop
    predicate := case t
      when 'pf_members' then 'user_id=auth.uid() and public.pf_member()'
      when 'pf_submissions' then 'public.pf_access(owner_id)'
      else 'public.pf_submission_access(submission_id)' end;
    execute format('drop policy if exists pf_read on public.%I',t);
    execute format('drop policy if exists pf_read_guard on public.%I',t);
    execute format('drop policy if exists pf_insert_guard on public.%I',t);
    execute format('drop policy if exists pf_update_guard on public.%I',t);
    execute format('drop policy if exists pf_delete_guard on public.%I',t);
    execute format('create policy pf_read on public.%I for select to authenticated using (%s)',t,predicate);
    execute format('create policy pf_read_guard on public.%I as restrictive for select to authenticated using (%s)',t,predicate);
    execute format('create policy pf_insert_guard on public.%I as restrictive for insert to authenticated with check (false)',t);
    execute format('create policy pf_update_guard on public.%I as restrictive for update to authenticated using (false) with check (false)',t);
    execute format('create policy pf_delete_guard on public.%I as restrictive for delete to authenticated using (false)',t);
  end loop;
end $$;

create or replace function public.pf_payload(p jsonb) returns jsonb
language plpgsql immutable set search_path = '' as $$
declare k text;
begin
  if jsonb_typeof(p)<>'object' or octet_length(p::text)>262144 then
    raise exception 'invalid payload';
  end if;
  for k in select jsonb_object_keys(p) loop
    if k not in ('factor_id','version','title','formula','license','code_hash','config_hash','data_hash','metrics','blockers','verification_stage') then
      raise exception 'forbidden payload field';
    end if;
  end loop;
  if coalesce(p->>'factor_id','') !~ '^[A-Za-z0-9_.:-]{1,160}$'
    or coalesce(p->>'version','') !~ '^[1-9][0-9]{0,5}$'
    or length(btrim(coalesce(p->>'title',''))) not between 1 and 200
    or length(btrim(coalesce(p->>'formula',''))) not between 1 and 4000
    or length(btrim(coalesce(p->>'license',''))) not between 1 and 4000
    or coalesce(p->>'verification_stage','') not in ('implemented','partial_proof','internal_validated')
    or jsonb_typeof(coalesce(p->'metrics','{}'::jsonb))<>'object'
    or jsonb_typeof(coalesce(p->'blockers','[]'::jsonb))<>'array' then
    raise exception 'invalid factor metadata';
  end if;
  foreach k in array array['code_hash','config_hash','data_hash'] loop
    if coalesce(p->>k,'')<>'' and p->>k !~ '^[0-9a-f]{64}$' then
      raise exception 'invalid hash';
    end if;
  end loop;
  return p;
end $$;

create or replace function public.pf_create(p_payload jsonb) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p jsonb; s public.pf_submissions;
begin
  if not public.pf_member() then raise exception 'not an active invited member'; end if;
  p := public.pf_payload(p_payload);
  insert into public.pf_submissions(owner_id,factor_id,version,title,formula,license,
    code_hash,config_hash,data_hash,metrics,blockers,verification_stage)
  values(auth.uid(),p->>'factor_id',(p->>'version')::integer,p->>'title',p->>'formula',p->>'license',
    coalesce(p->>'code_hash',''),coalesce(p->>'config_hash',''),coalesce(p->>'data_hash',''),
    coalesce(p->'metrics','{}'),coalesce(p->'blockers','[]'),p->>'verification_stage')
  returning * into s;
  insert into public.pf_audit(submission_id,actor_id,action) values(s.id,auth.uid(),'create');
  return to_jsonb(s);
end $$;

create or replace function public.pf_update(p_id uuid,p_payload jsonb) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p jsonb; s public.pf_submissions;
begin
  select * into s from public.pf_submissions where id=p_id for update;
  if not found or not public.pf_member() or s.owner_id<>auth.uid() or s.state<>'draft' then
    raise exception 'draft owner required';
  end if;
  p:=public.pf_payload(p_payload);
  if p->>'factor_id'<>s.factor_id or (p->>'version')::integer<>s.version then
    raise exception 'identity immutable';
  end if;
  update public.pf_submissions set title=p->>'title',formula=p->>'formula',license=p->>'license',
    code_hash=coalesce(p->>'code_hash',''),config_hash=coalesce(p->>'config_hash',''),
    data_hash=coalesce(p->>'data_hash',''),metrics=coalesce(p->'metrics','{}'),
    blockers=coalesce(p->'blockers','[]'),verification_stage=p->>'verification_stage',updated_at=now()
    where id=p_id returning * into s;
  insert into public.pf_audit(submission_id,actor_id,action) values(p_id,auth.uid(),'edit_draft');
  return to_jsonb(s);
end $$;

create or replace function public.pf_reserve_file(p_id uuid,p_name text,p_size bigint,p_sha256 text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare s public.pf_submissions; f public.pf_files; fid uuid:=gen_random_uuid(); ext text;
begin
  select * into s from public.pf_submissions where id=p_id for update;
  if not found or not public.pf_member() or s.owner_id<>auth.uid() or s.state<>'draft' then
    raise exception 'draft owner required';
  end if;
  perform pg_advisory_xact_lock(hashtextextended(p_id::text,0));
  if p_name is null or length(p_name) not between 1 and 160 or p_name ~ '[\\/:]' or p_name ~ '[[:cntrl:]]'
    or p_name like '%..%' or p_size not between 1 and 26214400
    or p_sha256 is null or p_sha256 !~ '^[0-9a-f]{64}$' then raise exception 'invalid file'; end if;
  ext:=lower(substring(p_name from '\.([^.]+)$'));
  if ext is null or ext not in ('py','json','md','pdf','csv','parquet') then raise exception 'file type forbidden'; end if;
  if (select coalesce(sum(size_bytes),0) from public.pf_files where submission_id=p_id)+p_size>104857600 then
    raise exception 'version file quota exceeded';
  end if;
  insert into public.pf_files(id,submission_id,name,object_path,size_bytes,sha256)
    values(fid,p_id,p_name,p_id::text||'/'||fid::text||'.'||ext,p_size,p_sha256) returning * into f;
  insert into public.pf_audit(submission_id,actor_id,action) values(p_id,auth.uid(),'reserve_file');
  return to_jsonb(f);
end $$;

create or replace function public.pf_storage_read(p_name text) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists(select 1 from public.pf_files f join public.pf_submissions s on s.id=f.submission_id
    where f.object_path=p_name and public.pf_access(s.owner_id))
$$;
create or replace function public.pf_storage_write(p_name text) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists(select 1 from public.pf_files f join public.pf_submissions s on s.id=f.submission_id
    where f.object_path=p_name and f.status='reserved' and s.state='draft'
      and s.owner_id=auth.uid() and public.pf_member())
$$;

insert into storage.buckets(id,name,public,file_size_limit,allowed_mime_types)
values('factor-private-submissions','factor-private-submissions',false,26214400,
  array['text/plain','text/x-python','application/json','text/markdown','application/pdf','text/csv','application/octet-stream'])
on conflict(id) do update set public=false,file_size_limit=26214400,allowed_mime_types=excluded.allowed_mime_types;
drop policy if exists pf_storage_select on storage.objects;
drop policy if exists pf_storage_insert on storage.objects;
drop policy if exists pf_storage_read_guard on storage.objects;
drop policy if exists pf_storage_write_guard on storage.objects;
drop policy if exists pf_storage_update_guard on storage.objects;
drop policy if exists pf_storage_delete_guard on storage.objects;
create policy pf_storage_select on storage.objects for select to authenticated
  using(bucket_id='factor-private-submissions' and public.pf_storage_read(name));
create policy pf_storage_insert on storage.objects for insert to authenticated
  with check(bucket_id='factor-private-submissions' and public.pf_storage_write(name));
create policy pf_storage_read_guard on storage.objects as restrictive for select to anon,authenticated
  using(bucket_id<>'factor-private-submissions' or public.pf_storage_read(name));
create policy pf_storage_write_guard on storage.objects as restrictive for insert to anon,authenticated
  with check(bucket_id<>'factor-private-submissions' or public.pf_storage_write(name));
create policy pf_storage_update_guard on storage.objects as restrictive for update to anon,authenticated
  using(bucket_id<>'factor-private-submissions') with check(bucket_id<>'factor-private-submissions');
create policy pf_storage_delete_guard on storage.objects as restrictive for delete to anon,authenticated
  using(bucket_id<>'factor-private-submissions');

create or replace function public.pf_finish_file(p_file_id uuid) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare f public.pf_files; s public.pf_submissions; actual_size bigint;
begin
  select * into f from public.pf_files where id=p_file_id;
  select * into s from public.pf_submissions where id=f.submission_id for update;
  if s.id is null or not public.pf_member() or s.owner_id<>auth.uid() or s.state<>'draft' then
    raise exception 'draft owner required';
  end if;
  select (metadata->>'size')::bigint into actual_size from storage.objects
    where bucket_id='factor-private-submissions' and name=f.object_path;
  if actual_size is null or actual_size<>f.size_bytes then raise exception 'uploaded object size mismatch'; end if;
  update public.pf_files set status='uploaded' where id=p_file_id returning * into f;
  insert into public.pf_audit(submission_id,actor_id,action) values(s.id,auth.uid(),'finish_upload');
  return to_jsonb(f);
end $$;

create or replace function public.pf_submit(p_id uuid) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare s public.pf_submissions; manifest jsonb; files jsonb;
begin
  select * into s from public.pf_submissions where id=p_id for update;
  if not found or not public.pf_member() or s.owner_id<>auth.uid() then raise exception 'owner required'; end if;
  if s.state<>'draft' and s.frozen_hash is not null then return to_jsonb(s); end if;
  if s.state<>'draft' then raise exception 'not a draft'; end if;
  if s.code_hash !~ '^[0-9a-f]{64}$' or s.config_hash !~ '^[0-9a-f]{64}$' or s.data_hash !~ '^[0-9a-f]{64}$' then
    raise exception 'code config and data hashes required';
  end if;
  if not exists(select 1 from public.pf_files where submission_id=p_id)
    or exists(select 1 from public.pf_files where submission_id=p_id and status='reserved') then
    raise exception 'complete uploaded evidence required';
  end if;
  select jsonb_agg(jsonb_build_object('id',id,'name',name,'sha256',sha256,'size',size_bytes) order by id)
    into files from public.pf_files where submission_id=p_id;
  manifest:=jsonb_build_object('factor_id',s.factor_id,'version',s.version,'title',s.title,
    'formula',s.formula,'license',s.license,'code_hash',s.code_hash,'config_hash',s.config_hash,
    'data_hash',s.data_hash,'metrics',s.metrics,'blockers',s.blockers,'verification_stage',s.verification_stage,'files',files);
  update public.pf_submissions set state='submitted',submitted_at=now(),updated_at=now(),
    frozen_manifest=manifest,frozen_hash=encode(sha256(convert_to(manifest::text,'UTF8')),'hex')
    where id=p_id returning * into s;
  insert into public.pf_audit(submission_id,actor_id,action) values(p_id,auth.uid(),'submit');
  return to_jsonb(s);
end $$;

create or replace function public.pf_begin_review(p_id uuid) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare s public.pf_submissions;
begin
  if not public.pf_admin() then raise exception 'MFA administrator required'; end if;
  select * into s from public.pf_submissions where id=p_id for update;
  if not found or s.owner_id=auth.uid() then raise exception 'independent reviewer required'; end if;
  if s.state='under_review' and s.reviewer_id=auth.uid() then return to_jsonb(s); end if;
  if s.state<>'submitted' then raise exception 'submitted version required'; end if;
  update public.pf_submissions set state='under_review',reviewer_id=auth.uid(),updated_at=now()
    where id=p_id returning * into s;
  insert into public.pf_audit(submission_id,actor_id,action) values(p_id,auth.uid(),'begin_review');
  return to_jsonb(s);
end $$;

create or replace function public.pf_check_file(p_file_id uuid,p_sha256 text,p_note text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare f public.pf_files; s public.pf_submissions;
begin
  if not public.pf_admin() then raise exception 'MFA administrator required'; end if;
  select * into f from public.pf_files where id=p_file_id;
  select * into s from public.pf_submissions where id=f.submission_id for update;
  if s.id is null or s.state<>'under_review' or s.owner_id=auth.uid() or s.reviewer_id<>auth.uid()
    or f.status='reserved' or p_sha256 is distinct from f.sha256
    or length(btrim(coalesce(p_note,''))) not between 1 and 4000 then
    raise exception 'independent file inspection and matching hash required';
  end if;
  update public.pf_files set status='manually_checked',checked_by=auth.uid(),checked_at=now(),check_note=p_note
    where id=p_file_id returning * into f;
  insert into public.pf_audit(submission_id,actor_id,action) values(s.id,auth.uid(),'manual_file_inspection');
  return to_jsonb(f);
end $$;

create or replace function public.pf_review(p_id uuid,p_decision text,p_note text,p_attestation jsonb) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare s public.pf_submissions; gate text;
begin
  if not public.pf_admin() then raise exception 'MFA administrator required'; end if;
  select * into s from public.pf_submissions where id=p_id for update;
  if not found or s.owner_id=auth.uid() or s.reviewer_id<>auth.uid() or s.state<>'under_review' then
    raise exception 'assigned independent reviewer required';
  end if;
  if p_decision is null or p_decision not in ('admitted','returned','rejected')
    or length(btrim(coalesce(p_note,''))) not between 1 and 4000
    or p_attestation is null or jsonb_typeof(p_attestation)<>'object'
    or octet_length(p_attestation::text)>16384 then raise exception 'invalid decision'; end if;
  if p_decision='admitted' then
    if s.verification_stage<>'internal_validated' or jsonb_array_length(s.blockers)>0
      or exists(select 1 from public.pf_files where submission_id=p_id and status<>'manually_checked')
      or length(btrim(coalesce(p_attestation->>'independent_node','')))=0
      or length(btrim(coalesce(p_attestation->>'evidence_reference','')))=0 then
      raise exception 'admission evidence incomplete';
    end if;
    foreach gate in array array['data_quality','executability','statistics','redundancy','costs',
      'risk','platform','code_review','independent_reproduction'] loop
      if p_attestation->gate is distinct from 'true'::jsonb then raise exception 'admission gate incomplete'; end if;
    end loop;
  end if;
  insert into public.pf_reviews(submission_id,reviewer_id,decision,note,attestation)
    values(p_id,auth.uid(),p_decision,p_note,p_attestation);
  update public.pf_submissions set state=p_decision,updated_at=now() where id=p_id returning * into s;
  insert into public.pf_audit(submission_id,actor_id,action) values(p_id,auth.uid(),p_decision);
  return to_jsonb(s);
end $$;

-- No RPC may inherit PostgreSQL's default PUBLIC execution privilege.
do $$
declare f record;
begin
  for f in select oid::regprocedure as signature,proname from pg_proc
    where pronamespace='public'::regnamespace and proname like 'pf\_%' escape '\' loop
    execute format('revoke all on function %s from public,anon,authenticated',f.signature);
    if f.proname<>'pf_payload' then
      execute format('grant execute on function %s to authenticated',f.signature);
    end if;
    if f.proname in ('pf_member','pf_admin','pf_access','pf_submission_access','pf_storage_read','pf_storage_write') then
      execute format('grant execute on function %s to anon',f.signature);
    end if;
  end loop;
end $$;
commit;
