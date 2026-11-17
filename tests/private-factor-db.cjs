// Run against an ephemeral PGlite PostgreSQL, never the configured cloud database.
const { PGlite } = require(process.argv[2]);
const fs = require("node:fs");
const assert = require("node:assert/strict");

(async () => {
  const db = new PGlite();
  const A = "10000000-0000-0000-0000-000000000001";
  const B = "10000000-0000-0000-0000-000000000002";
  const ADMIN = "10000000-0000-0000-0000-000000000003";
  let checks = 0;
  await db.exec(`
    create role anon;
    create role authenticated;
    create role service_role bypassrls;
    create schema auth;
    create schema storage;
    create table auth.users(id uuid primary key, email_confirmed_at timestamptz default now());
    create function auth.uid() returns uuid language sql stable as
      $$select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid$$;
    create function auth.jwt() returns jsonb language sql stable as
      $$select coalesce(nullif(current_setting('request.jwt.claims',true),''),'{}')::jsonb$$;
    grant usage on schema auth,storage to authenticated,anon;
    grant execute on all functions in schema auth to authenticated,anon;
    create table storage.buckets(id text primary key,name text,public boolean,
      file_size_limit bigint,allowed_mime_types text[]);
    create table storage.objects(id uuid default gen_random_uuid(),bucket_id text,
      name text,metadata jsonb,primary key(bucket_id,name));
    alter table storage.objects enable row level security;
    grant select,insert,update,delete on storage.objects to authenticated;
    insert into auth.users(id) values('${A}'),('${B}'),('${ADMIN}');
  `);
  const sql = fs.readFileSync(process.argv[3], "utf8");
  await db.exec(sql);
  // Reapplication must preserve records and remain idempotent.
  await db.exec(sql);
  const passwordOnly = !!process.argv[4];
  if(passwordOnly) {
    const incremental=fs.readFileSync(process.argv[4],"utf8");
    await db.exec(incremental);
    await db.exec(incremental);
  }
  await db.exec(`insert into public.pf_members(user_id,role) values
    ('${A}','collaborator'),('${B}','collaborator'),('${ADMIN}','admin')`);
  async function user(id, aal = "aal1") {
    await db.exec("reset role");
    await db.query("select set_config('request.jwt.claim.sub',$1,false)", [id || ""]);
    await db.query("select set_config('request.jwt.claims',$1,false)", [JSON.stringify({ aal })]);
    await db.exec(`set role ${id ? "authenticated" : "anon"}`);
  }
  async function denied(query, args = []) {
    await assert.rejects(() => db.query(query, args));
    checks++;
  }
  const draft = {factor_id:"JQGM:turnover_ratio_40d",version:1,title:"turnover40",
    formula:"Mean(turnover,40)",license:"author owns uploaded implementation",
    verification_stage:"partial_proof",blockers:["missing execution evidence"],
    code_hash:"a".repeat(64),config_hash:"b".repeat(64),data_hash:"c".repeat(64),
    metrics:{rank_ic:-.04}};
  await user(null);
  await denied("select public.pf_create($1::jsonb)", [JSON.stringify(draft)]);
  await user(A);
  await denied("select public.pf_create($1::jsonb)", [JSON.stringify({...draft,owner_id:B})]);
  const created = (await db.query("select public.pf_create($1::jsonb) as r", [JSON.stringify(draft)])).rows[0].r;
  const id = created.id;
  assert.equal(created.owner_id, A); checks++;
  await denied("update public.pf_submissions set state='admitted' where id=$1", [id]);
  await denied("update public.pf_members set role='admin' where user_id=$1", [A]);
  const file = (await db.query("select public.pf_reserve_file($1,$2,$3,$4) as r",
    [id,"factor.py",11,"d".repeat(64)])).rows[0].r;
  await denied("select public.pf_reserve_file($1,$2,$3,$4)",[id,"../factor.py",1,"d".repeat(64)]);
  await denied("select public.pf_reserve_file($1,$2,$3,$4)",[id,"factor.zip",1,"d".repeat(64)]);
  await denied("select public.pf_reserve_file($1,$2,$3,$4)",[id,"factor.py",26*1024*1024,"d".repeat(64)]);
  await user(B);
  assert.equal((await db.query("select * from public.pf_submissions")).rows.length,0); checks++;
  assert.equal((await db.query("select * from public.pf_files")).rows.length,0); checks++;
  await denied("select public.pf_update($1,$2::jsonb)",[id,JSON.stringify(draft)]);
  await denied("select public.pf_submit($1)",[id]);
  await denied("insert into storage.objects(bucket_id,name,metadata) values($1,$2,$3)",
    ["factor-private-submissions",file.object_path,JSON.stringify({size:11})]);
  await user(A);
  await db.query("insert into storage.objects(bucket_id,name,metadata) values($1,$2,$3)",
    ["factor-private-submissions",file.object_path,JSON.stringify({size:11})]);
  await db.query("select public.pf_finish_file($1)",[file.id]);
  const submitted = (await db.query("select public.pf_submit($1) as r",[id])).rows[0].r;
  assert.equal(submitted.state,"submitted"); checks++;
  assert.equal(submitted.frozen_hash.length,64); checks++;
  assert.equal((await db.query("select public.pf_submit($1) as r",[id])).rows[0].r.frozen_hash,
    submitted.frozen_hash); checks++;
  await denied("select public.pf_update($1,$2::jsonb)",[id,JSON.stringify(draft)]);
  assert.equal((await db.query("update storage.objects set metadata='{}' where name=$1 returning name",
    [file.object_path])).rows.length,0); checks++;
  await user(B);
  assert.equal((await db.query("select * from storage.objects")).rows.length,0); checks++;
  assert.equal((await db.query("select * from public.pf_audit")).rows.length,0); checks++;
  await user(ADMIN);
  if(passwordOnly) {
    assert.equal((await db.query("select * from public.pf_submissions")).rows.length,1); checks++;
    await db.exec("reset role");
    await db.query("update auth.users set email_confirmed_at=null where id=$1",[ADMIN]);
    await user(ADMIN,"aal2");
    assert.equal((await db.query("select public.pf_admin() as allowed")).rows[0].allowed,false); checks++;
    await denied("select public.pf_begin_review($1)",[id]);
    await db.exec("reset role");
    await db.query("update auth.users set email_confirmed_at=now() where id=$1",[ADMIN]);
    await user(ADMIN);
    await db.query("select public.pf_begin_review($1)",[id]);
  } else {
    assert.equal((await db.query("select * from public.pf_submissions")).rows.length,0); checks++;
    await denied("select public.pf_begin_review($1)",[id]);
  }
  await user(ADMIN,"aal2");
  assert.equal((await db.query("select * from public.pf_submissions")).rows.length,1); checks++;
  await db.query("select public.pf_begin_review($1)",[id]);
  await db.query("select public.pf_check_file($1,$2,$3)",[file.id,"d".repeat(64),"manual inspection only, not executed"]);
  await denied("select public.pf_review($1,$2,$3,$4::jsonb)",[id,"admitted","approve",JSON.stringify({})]);
  const returned = (await db.query("select public.pf_review($1,$2,$3,$4::jsonb) as r",
    [id,"returned","complete execution evidence",JSON.stringify({})])).rows[0].r;
  assert.equal(returned.state,"returned"); checks++;
  await user(A);
  assert.equal((await db.query("select * from public.pf_reviews")).rows.length,1); checks++;
  const own = (await db.query("select public.pf_create($1::jsonb) as r",
    [JSON.stringify({...draft,version:2})])).rows[0].r;
  await user(ADMIN,"aal2");
  const adminOwn = (await db.query("select public.pf_create($1::jsonb) as r",
    [JSON.stringify(draft)])).rows[0].r;
  await denied("select public.pf_begin_review($1)",[adminOwn.id]);
  // Check successful private admission separately from the partial turnover40 case.
  await user(A);
  const ready = (await db.query("select public.pf_create($1::jsonb) as r",
    [JSON.stringify({...draft,version:3,verification_stage:"internal_validated",blockers:[]})])).rows[0].r;
  await denied("select public.pf_submit($1)",[ready.id]);
  const complete = (await db.query("select public.pf_reserve_file($1,$2,$3,$4) as r",
    [ready.id,"evidence.json",3,"e".repeat(64)])).rows[0].r;
  await db.query("insert into storage.objects(bucket_id,name,metadata) values($1,$2,$3)",
    ["factor-private-submissions",complete.object_path,JSON.stringify({size:2})]);
  await denied("select public.pf_finish_file($1)",[complete.id]);
  await db.exec("reset role");
  await db.query("update storage.objects set metadata=$1 where name=$2",
    [JSON.stringify({size:3}),complete.object_path]);
  await user(A);
  await db.query("select public.pf_finish_file($1)",[complete.id]);
  await db.query("select public.pf_submit($1)",[ready.id]);
  await user(ADMIN,"aal2");
  await db.query("select public.pf_begin_review($1)",[ready.id]);
  const gates = Object.fromEntries(["data_quality","executability","statistics","redundancy","costs",
    "risk","platform","code_review","independent_reproduction"].map(key=>[key,true]));
  gates.independent_node="review-node";
  gates.evidence_reference="test-only-local-reference";
  await denied("select public.pf_review($1,$2,$3,$4::jsonb)",
    [ready.id,"admitted","test attestation",JSON.stringify(gates)]);
  await db.query("select public.pf_check_file($1,$2,$3)",[complete.id,"e".repeat(64),"test inspection"]);
  const admitted=(await db.query("select public.pf_review($1,$2,$3,$4::jsonb) as r",
    [ready.id,"admitted","test attestation",JSON.stringify(gates)])).rows[0].r;
  assert.equal(admitted.state,"admitted"); checks++;
  await user(B);
  assert.equal((await db.query("select * from public.pf_submissions where id=$1",[ready.id])).rows.length,0); checks++;
  await db.exec("reset role");
  assert.equal((await db.query("select public from storage.buckets where id='factor-private-submissions'")).rows[0].public,false);
  checks++;
  // Existing permissive storage policies are OR-ed: a restrictive guard must still block new bucket access.
  await db.exec(`create policy old_allow_all on storage.objects for all to authenticated using(true) with check(true)`);
  await db.exec(`grant insert,update,delete on public.pf_submissions to authenticated;
    create policy old_submission_allow_all on public.pf_submissions for all to authenticated using(true) with check(true)`);
  await user(B);
  assert.equal((await db.query("select * from storage.objects")).rows.length,0); checks++;
  assert.equal((await db.query("select * from public.pf_submissions")).rows.length,0); checks++;
  await denied("insert into public.pf_submissions(owner_id,factor_id,version,title,formula,license,verification_stage) values($1,'forged',1,'x','x','x','implemented')",[B]);
  await denied("insert into storage.objects(bucket_id,name,metadata) values($1,$2,'{}')",
    ["factor-private-submissions",file.object_path+"fake"]);
  await db.exec("reset role");
  await db.query("update public.pf_members set active=false where user_id=$1",[A]);
  await user(A);
  assert.equal((await db.query("select * from public.pf_submissions")).rows.length,0); checks++;
  await denied("select public.pf_submit($1)",[own.id]);
  await db.close();
  console.log(JSON.stringify({postgres:"PGlite",checks,identities:["anon","A","B","admin_aal1","admin_aal2"],
    result:"passed",scope:"local PostgreSQL; not cloud deployment validation"}));
})().catch(error => { console.error(error); process.exitCode=1; });
