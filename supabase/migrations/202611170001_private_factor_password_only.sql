-- User-approved temporary policy: confirmed email + authenticated account,
-- without workbench MFA. Owner isolation and independent review are unchanged.
begin;

create or replace function public.pf_member() returns boolean
language sql stable security definer set search_path = '' as $$
  select exists(
    select 1 from public.pf_members m
    join auth.users u on u.id=m.user_id
    where m.user_id=auth.uid() and m.active
      and u.email_confirmed_at is not null
  )
$$;

create or replace function public.pf_admin() returns boolean
language sql stable security definer set search_path = '' as $$
  select exists(
    select 1 from public.pf_members m
    join auth.users u on u.id=m.user_id
    where m.user_id=auth.uid() and m.active and m.role='admin'
      and u.email_confirmed_at is not null
  )
$$;

-- Keep explicit execution privileges; no direct table writes are introduced.
revoke all on function public.pf_member(), public.pf_admin() from public;
grant execute on function public.pf_member(), public.pf_admin() to anon,authenticated;
commit;
