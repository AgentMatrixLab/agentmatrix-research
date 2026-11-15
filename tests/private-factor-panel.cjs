// Offline DOM interaction check; PostgreSQL authorization is tested separately.
const fs = require("node:fs");
const assert = require("node:assert/strict");
const path = require("node:path");
const { pathToFileURL } = require("node:url");
const { parseHTML } = require(process.argv[2]);

(async () => {
  const { window, document } = parseHTML(fs.readFileSync("pages/factor-db-dashboard/submissions.html","utf8"));
  global.window=window; global.document=document;
  const $=id=>document.getElementById(id);
  const storage=new Map();
  window.sessionStorage={getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)};
  for(const form of document.querySelectorAll("form")) form.reset=()=>{};
  for(const select of document.querySelectorAll("select")) {
    let value=select.querySelector("option")?.value || "";
    Object.defineProperty(select,"value",{get:()=>value,set:v=>{value=String(v)},configurable:true});
  }
  window.FACTOR_LAB_SUPABASE_URL="https://test.supabase.co";
  window.FACTOR_LAB_SUPABASE_ANON_KEY="public-test-key";
  window.PRIVATE_FACTOR_BACKEND_ENABLED=true;
  let user=null, active=true, admin=false, fail=false, authEvent;
  const rows=[];
  const sdk={
    auth:{
      getUser:async()=>({data:{user},error:null}),
      signInWithPassword:async()=>{user={id:"owner-a",email:"a@example.test"};return {error:null}},
      signOut:async()=>{user=null;authEvent("SIGNED_OUT");return {error:null}},
      onAuthStateChange:fn=>{authEvent=fn;return {data:{subscription:{unsubscribe(){}}}}},
      mfa:{listFactors:async()=>({data:{all:[]},error:null})}
    },
    rpc:async(name,params)=>{
      if(fail) return {data:null,error:{message:"private schema not deployed"}};
      if(name==="pf_member") return {data:active,error:null};
      if(name==="pf_admin") return {data:admin,error:null};
      if(name==="pf_create") {
        const row={...params.p_payload,id:"receipt-1",owner_id:user.id,state:"draft"};
        rows.push(row);return {data:row,error:null};
      }
      return {error:{message:"unexpected operation"}};
    },
    from:table=>({select:()=>table==="pf_submissions"?
      {order:async()=>({data:rows,error:null})}:{eq:async()=>({data:[],error:null})}})
  };
  window.supabase={createClient:()=>sdk};
  await import(pathToFileURL(path.resolve("pages/factor-db-dashboard/submissions.js")));
  async function settle() { for(let i=0;i<12;i++) await new Promise(resolve=>setImmediate(resolve)); }
  function fire(id,event) { $(id).dispatchEvent(new window.Event(event,{cancelable:true})); }
  assert.equal($("workspace").hidden,true);
  $("email").value="a@example.test";$("password").value="test-password";
  fire("login-form","submit");await settle();
  assert.equal($("workspace").hidden,false);
  assert.equal($("password").value,"");
  $("factor-id").value="test:alpha";$("version").value="1";$("title").value="<script>private</script>";
  $("formula").value="Mean(x,40)";$("license").value="test only";
  for(const id of ["code-hash","config-hash","data-hash"]) $(id).value="a".repeat(64);
  $("verification-stage").value="partial_proof";$("metrics").value="{}";$("blockers").value='["missing"]';
  fire("draft-form","submit");await settle();
  assert.equal(rows.length,1);
  assert.equal($("submission-list").querySelector("script"),null);
  assert($("status").textContent.includes("尚未提交审核"));
  assert($("submission-detail").textContent.includes("receipt-1"));
  fire("logout","click");await settle();
  assert.equal($("workspace").hidden,true);
  assert.equal($("submission-list").children.length,0);
  assert.equal($("submission-detail").textContent,"");
  assert.equal($("mfa-secret").textContent,"");
  admin=true;active=false;
  fire("login-form","submit");await settle();
  assert.equal($("workspace").hidden,true);
  assert($("status").textContent.includes("MFA"));
  active=true;fail=true;
  fire("refresh","click");await settle();
  assert.equal($("workspace").hidden,true);
  assert($("status").textContent.includes("不会回退到演示数据"));
  console.log(JSON.stringify({dom_checks:14,result:"passed",
    scope:"login/upload-form/logout/error DOM logic; not browser rendering or real Auth"}));
})().catch(error=>{console.error(error);process.exitCode=1});
