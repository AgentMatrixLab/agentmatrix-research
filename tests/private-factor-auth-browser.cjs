// Real browser + real Supabase SDK; only network responses are deterministic fixtures.
// Live Auth/MFA acceptance is separate and must never use a user's password.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");
const {chromium} = require(process.argv[2] || "playwright");
const root = path.resolve("pages/factor-db-dashboard");
const userId = "11111111-1111-4111-8111-111111111111";
const factorId = "22222222-2222-4222-8222-222222222222";
const secret = "JBSWY3DPEHPK3PXP";
let browser;
const server = http.createServer((req,res)=>{
  const pathname = decodeURIComponent(new URL(req.url,"http://localhost").pathname);
  const file = path.resolve(root,"."+pathname);
  if(!file.startsWith(root+path.sep)) {res.writeHead(404).end();return;}
  fs.readFile(file,(error,data)=>{
    if(error) {res.writeHead(404).end();return;}
    res.setHeader("Content-Type",file.endsWith(".html")?"text/html":"application/javascript");
    res.end(data);
  });
});
function session(user,aal="aal1") {
  const now=Math.floor(Date.now()/1000);
  const claims={sub:userId,aud:"authenticated",role:"authenticated",aal,iat:now,exp:now+3600,
    amr:[{method:"password",timestamp:now}]};
  const jwt=Buffer.from('{"alg":"HS256","typ":"JWT"}').toString("base64url")+"."+
    Buffer.from(JSON.stringify(claims)).toString("base64url")+".fixture";
  return {access_token:jwt,refresh_token:"fixture-refresh-token",token_type:"bearer",
    expires_in:3600,expires_at:now+3600,user};
}
(async()=>{
  await new Promise(resolve=>server.listen(0,"127.0.0.1",resolve));
  browser=await chromium.launch({headless:true,
    ...(process.env.AMX_CHROMIUM_PATH?{executablePath:process.env.AMX_CHROMIUM_PATH}:{})});
  let checks=0;
  for(const scenario of ["short_password","successful_login","mfa_retry","refresh_failure","recovery_link"]) {
    if(process.env.AMX_AUTH_SCENARIO && process.env.AMX_AUTH_SCENARIO!==scenario) continue;
    const context=await browser.newContext();
    const page=await context.newPage();
    const calls=[],errors=[];
    let factors=[],aal="aal1",member=scenario!=="mfa_retry",userFailure=false;
    const user=()=>({id:userId,aud:"authenticated",role:"authenticated",email:"test@example.invalid",
      email_confirmed_at:"2026-01-01T00:00:00Z",created_at:"2026-01-01T00:00:00Z",
      app_metadata:{provider:"email",providers:["email"]},user_metadata:{},factors});
    page.on("pageerror",e=>errors.push(e.message));
    await page.route("**/private-config.js*",route=>route.fulfill({contentType:"application/javascript",
      body:'window.PRIVATE_FACTOR_BACKEND_ENABLED=true;window.FACTOR_LAB_SUPABASE_URL="https://test.supabase.co";window.FACTOR_LAB_SUPABASE_ANON_KEY="public-fixture";'}));
    await page.route("https://test.supabase.co/**",async route=>{
      const req=route.request(),url=new URL(req.url());
      if(req.method()==="OPTIONS") {
        await route.fulfill({status:204,headers:{"access-control-allow-origin":"*",
          "access-control-allow-headers":"*","access-control-allow-methods":"GET,POST,PUT,DELETE"}});return;
      }
      calls.push(url.pathname);
      let body={},status=200;
      if(url.pathname==="/auth/v1/token") body=session(user(),aal);
      else if(url.pathname==="/auth/v1/user") {
        body=user();
        if(userFailure) {status=503;body={code:"unexpected_failure",msg:"fixture service unavailable"};}
      } else if(url.pathname==="/rest/v1/rpc/pf_member") body=member;
      else if(url.pathname==="/rest/v1/rpc/pf_admin") body=aal==="aal2";
      else if(url.pathname==="/rest/v1/pf_submissions") body=[];
      else if(url.pathname==="/auth/v1/factors") {
        factors=[{id:factorId,factor_type:"totp",status:"unverified",friendly_name:"Test"}];
        body={id:factorId,type:"totp",totp:{secret,uri:"otpauth://fixture",qr_code:""}};
      } else if(url.pathname.endsWith("/challenge")) body={id:"fixture-challenge",expires_at:9999999999};
      else if(url.pathname.endsWith("/verify")) {
        if(req.postDataJSON().code==="000000") {status=422;body={code:"mfa_verification_failed",msg:"Invalid TOTP code"};}
        else {aal="aal2";member=true;factors[0].status="verified";body=session(user(),aal);}
      } else if(url.pathname==="/auth/v1/logout") status=204;
      else throw new Error("Uncovered request "+url.pathname);
      await route.fulfill({status,contentType:"application/json",
        headers:{"access-control-allow-origin":"*"},body:status===204?"":JSON.stringify(body)});
    });
    let url=`http://127.0.0.1:${server.address().port}/submissions.html`;
    if(scenario==="recovery_link") {
      const recovery=session(user());
      url+="#"+new URLSearchParams({access_token:recovery.access_token,refresh_token:recovery.refresh_token,
        token_type:"bearer",expires_in:"3600",type:"recovery"});
    }
    await page.goto(url,{waitUntil:"networkidle"});
    if(scenario==="recovery_link") {
      assert(await page.locator("#password-form").isVisible(),"recovery link opens password form");checks++;
      assert((await page.locator("#status").innerText()).includes("密码恢复链接已验证"),"recovery status is not overwritten");checks++;
      assert.equal(errors.length,0,"recovery has no browser errors");checks++;
      await context.close();
      console.log(JSON.stringify({scenario,result:"passed"}));
      continue;
    }
    await page.locator("#email").fill("test@example.invalid");
    await page.locator("#password").fill(scenario==="short_password"?"aB9!xy":"long-test-password");
    await page.locator("#login-form button.primary").click();
    await page.waitForFunction(()=>!document.getElementById("account-panel").hidden,{},{timeout:5000})
      .catch(()=>{throw new Error(`${scenario}: valid credentials must reach Auth and show the account panel`);});
    await page.waitForLoadState("networkidle");
    assert(calls.includes("/auth/v1/token"),`${scenario}: token request required`);checks++;
    assert.equal(errors.length,0,`${scenario}: browser errors`);checks++;
    if(scenario==="successful_login") {
      assert.equal(calls.filter(p=>p==="/rest/v1/rpc/pf_member").length,1,"login must initialize membership exactly once");checks++;
      assert((await page.locator("#status").innerText()).includes("已通过"),"success must not be overwritten by onboarding");checks++;
      await page.reload({waitUntil:"networkidle"});
      assert(await page.locator("#workspace").isVisible(),"reload retains authenticated workspace");checks++;
    }
    if(scenario==="mfa_retry") {
      assert(!(await page.locator("#workspace").isVisible()),"aal1 admin cannot read private workspace");checks++;
      assert(!calls.includes("/rest/v1/pf_submissions"),"no private list request before MFA");checks++;
      assert(await page.locator("#enroll-mfa").isVisible(),"MFA controls must open without searching");checks++;
      await page.reload({waitUntil:"networkidle"});
      assert(await page.locator("#enroll-mfa").isVisible(),"MFA controls must also open on reload");checks++;
      await page.locator("#enroll-mfa").click();
      await page.locator("#mfa-secret").waitFor({state:"visible"});
      assert(!(await page.locator("#status").innerText()).includes("正在处理"),"enrollment must finish its progress status");checks++;
      await page.locator("#mfa-code").fill("000000");
      await page.locator("#mfa-form button").click();
      await page.waitForFunction(()=>document.getElementById("status").textContent.includes("操作未完成"));
      assert(await page.locator("#mfa-secret").isVisible(),"failed TOTP must preserve the unverified setup secret");checks++;
      await page.locator("#mfa-code").fill("123456");
      await page.locator("#mfa-form button").click();
      await page.locator("#workspace").waitFor({state:"visible"});
      assert(!(await page.locator("#mfa-secret").isVisible()),"successful TOTP clears setup secret");checks++;
    }
    if(scenario==="refresh_failure") {
      userFailure=true;
      await page.locator("#refresh").click();
      await page.waitForFunction(()=>document.getElementById("status").textContent.includes("操作未完成"),{},{timeout:15000});
      assert(!(await page.locator("#workspace").isVisible()),"failed auth revalidation hides private data");checks++;
      userFailure=false;
      await context.close();
      console.log(JSON.stringify({scenario,result:"passed"}));
      continue;
    }
    await page.locator("#logout").click();
    await page.locator("#login-panel").waitFor({state:"visible"});
    assert(!(await page.locator("#workspace").isVisible()),"logout clears private workspace");checks++;
    await context.close();
    console.log(JSON.stringify({scenario,result:"passed"}));
  }
  console.log(JSON.stringify({browser_checks:checks,result:"passed",scope:"real Chromium/SDK; fixture network, not live Auth"}));
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{
  if(browser) await browser.close();
  server.close();
});
