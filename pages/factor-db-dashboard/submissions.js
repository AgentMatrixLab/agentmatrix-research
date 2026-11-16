import { PrivateFactorClient, draftPayload, fileDigest, validateFile } from "./submission-client.mjs";

const $ = id => document.getElementById(id);
const STATES = {draft:"草稿",submitted:"待审核",under_review:"审核中",admitted:"已入库／仍私有",
  returned:"退回补证",rejected:"已拒绝"};
let api, sdk, currentUser, selected, records = [], files = [], isAdmin = false, generation = 0;
let passwordRecovery = false;
const downloaded = new Set();
const text = (tag,value) => { const node=document.createElement(tag); node.textContent=value; return node; };
const status = message => { $("status").textContent=message; };
const pretty = value => JSON.stringify(value,null,2);

function clearPrivate() {
  generation++;
  currentUser=null; selected=null; records=[]; files=[]; isAdmin=false; downloaded.clear();
  $("workspace").hidden=true; $("account-panel").hidden=true; $("logout").hidden=true;
  $("submission-list").replaceChildren(); $("file-list").replaceChildren();
  $("submission-detail").textContent=""; $("review-history").textContent="";
  $("mfa-secret").textContent=""; $("mfa-secret").hidden=true; $("mfa-factor").replaceChildren();
  $("identity").textContent="账号"; $("selected-label").textContent="请先选择或保存草稿。";
  $("draft-form").reset(); $("review-note").value=""; $("attestation").value="{}";
  $("upload-files").value=""; $("import-manifest").value=""; $("new-password").value=""; $("mfa-code").value="";
}

async function action(fn) {
  const buttons=[...document.querySelectorAll("button")];
  buttons.forEach(button=>{button.disabled=true});
  status("正在处理，请稍候…");
  try { await fn(); }
  catch(error) { status("操作未完成："+error.message+"。不会回退到演示数据。"); }
  finally {
    buttons.forEach(button=>{button.disabled=false});
    if($("status").textContent==="正在处理，请稍候…") status("操作完成。");
  }
}

function payloadFromForm() {
  return draftPayload({
    factor_id:$("factor-id").value.trim(),version:Number($("version").value),title:$("title").value,
    formula:$("formula").value,license:$("license").value,code_hash:$("code-hash").value.trim(),
    config_hash:$("config-hash").value.trim(),data_hash:$("data-hash").value.trim(),
    verification_stage:$("verification-stage").value,metrics:JSON.parse($("metrics").value),
    blockers:JSON.parse($("blockers").value)
  });
}

function fillForm(value) {
  const mapping={"factor-id":"factor_id",version:"version",title:"title",formula:"formula",
    license:"license","code-hash":"code_hash","config-hash":"config_hash","data-hash":"data_hash",
    "verification-stage":"verification_stage"};
  for(const [id,key] of Object.entries(mapping)) $(id).value=value[key] ?? "";
  $("metrics").value=pretty(value.metrics || {}); $("blockers").value=pretty(value.blockers || []);
}

function renderList() {
  $("submission-list").replaceChildren();
  const search=$("search").value.trim().toLowerCase();
  const visible=records.filter(s=>`${s.title} ${s.factor_id} ${STATES[s.state]}`.toLowerCase().includes(search));
  for(const s of visible) {
    const row=document.createElement("tr");
    const button=text("button","查看");
    button.addEventListener("click",()=>action(()=>select(s)));
    const control=document.createElement("td"); control.append(button);
    row.append(text("td",`${s.title} · ${s.factor_id} v${s.version}`),
      text("td",s.verification_stage),text("td",STATES[s.state] || s.state),control);
    $("submission-list").append(row);
  }
  if(!visible.length) $("submission-list").append(text("tr","当前账号没有匹配的私有提交。"));
}

async function select(row) {
  const epoch=generation;
  const [attachments,reviews,audit]=await Promise.all(["pf_files","pf_reviews","pf_audit"].map(t=>api.related(t,row.id)));
  if(epoch!==generation || !currentUser) return;
  selected=row; files=attachments; downloaded.clear();
  $("selected-label").textContent=`${row.factor_id} v${row.version} · ${STATES[row.state]} · 回执ID ${row.id}`;
  $("submission-detail").textContent=pretty(row);
  $("review-history").textContent=pretty({reviews,audit});
  $("review-panel").hidden=!isAdmin || row.owner_id===currentUser.id;
  $("save-draft").textContent=row.state==="draft" && row.owner_id===currentUser.id ? "保存当前草稿" : "保存新版本草稿";
  if(row.owner_id===currentUser.id) fillForm(row);
  renderFiles();
}

function renderFiles() {
  $("file-list").replaceChildren();
  for(const file of files) {
    const block=document.createElement("div");
    block.append(text("p",`${file.name} · ${file.size_bytes}字节 · ${file.status}`),text("code",file.sha256));
    const button=text("button","认证下载并核验哈希");
    button.addEventListener("click",()=>action(async()=>{
      const epoch=generation;
      const blob=await api.download(file);
      if(epoch!==generation || !currentUser) return;
      downloaded.add(file.id);
      const url=URL.createObjectURL(blob);
      const a=document.createElement("a"); a.href=url; a.download=file.name; a.click(); URL.revokeObjectURL(url);
      status("附件哈希已核验；仅下载，不会执行或在主站渲染。"); renderFiles();
    }));
    block.append(button);
    if(isAdmin && selected.state==="under_review" && selected.reviewer_id===currentUser.id &&
        selected.owner_id!==currentUser.id) {
      const check=text("button","记录人工检查");
      check.disabled=!downloaded.has(file.id);
      check.addEventListener("click",()=>action(async()=>{
        if(!downloaded.has(file.id)) throw new Error("请先下载并核验文件");
        const note=window.prompt("请记录实际人工内容检查结论；不能把下载成功当作代码安全审查。");
        if(!note?.trim()) throw new Error("人工检查说明必填");
        await api.checkFile(file,note); await reload(selected.id);
        status("已记录人工检查，不代表自动扫描通过。");
      }));
      block.append(check);
    }
    $("file-list").append(block);
  }
}

async function reload(selectId) {
  const epoch=generation;
  const next=await api.list();
  if(epoch!==generation || !currentUser) return;
  records=next; renderList();
  const match=records.find(s=>s.id===selectId);
  if(match) await select(match);
}

async function showSession() {
  clearPrivate();
  const epoch=generation;
  const {data,error}=await sdk.auth.getUser();
  if(epoch!==generation) return;
  if(error || !data.user) {
    $("login-panel").hidden=false;
    if(error && error.name!=="AuthSessionMissingError" && ![400,401,403].includes(error.status)) {
      throw new Error("账号服务暂时不可用，请检查网络后重试；这不代表密码错误。");
    }
    status("请使用受邀账号登录。"); return;
  }
  currentUser=data.user;
  $("login-panel").hidden=true; $("account-panel").hidden=false; $("logout").hidden=false;
  $("identity").textContent=`${currentUser.email} · 真实账号`;
  const factors=await sdk.auth.mfa.listFactors();
  if(epoch!==generation) return;
  if(factors.error) throw new Error(factors.error.message);
  for(const factor of factors.data.all.filter(f=>f.factor_type==="totp")) {
    const option=text("option",factor.friendly_name || factor.id); option.value=factor.id;
    $("mfa-factor").append(option);
  }
  const allowed=await api.rpc("pf_member",{});
  if(epoch!==generation) return;
  if(!allowed) {
    $("account-setup").open=true;
    status("密码登录已成功。管理员请完成下方MFA二次验证后进入工作区；若你是协作者，请联系管理员确认成员授权。"); return;
  }
  isAdmin=await api.rpc("pf_admin",{});
  if(epoch!==generation) return;
  $("list-title").textContent=isAdmin ? "管理员 · 待审核及全部私有提交" : "我的私有提交";
  $("workspace").hidden=false;
  await reload();
  if(epoch!==generation) return;
  if(passwordRecovery) {
    $("account-setup").open=true;
    status("密码恢复链接已验证，请在账号设置中填写新密码。");
  } else {
    status("已通过真实认证和成员权限。列表仅包含当前身份可访问的记录。");
  }
}

$("login-form").addEventListener("submit",event=>{
  event.preventDefault(); action(async()=>{
    const {error}=await sdk.auth.signInWithPassword({email:$("email").value.trim(),password:$("password").value});
    $("password").value="";
    if(error) {
      const invalid = error.code === "invalid_credentials" || /invalid login credentials/i.test(error.message);
      throw new Error(invalid ? "邮箱或独立密码不正确；首次使用请打开邀请邮件激活并设置密码，也可点击“首次设置／找回密码”。共享访问密码不能用于此账号。" : error.message);
    }
    await showSession();
  });
});
$("recover-password").addEventListener("click",()=>action(async()=>{
  const email=$("email").value.trim();
  if(!email || !$("email").checkValidity()) throw new Error("请先填写有效邮箱");
  const redirectTo=window.location.origin+window.location.pathname;
  const {error}=await sdk.auth.resetPasswordForEmail(email,{redirectTo});
  if(error) throw new Error(error.message);
  status("如果该邮箱已有受邀账号，系统会发送密码设置邮件。请从邮件中的链接进入，再设置独立密码；未收到请检查垃圾邮件。");
}));
$("logout").addEventListener("click",()=>action(async()=>{
  passwordRecovery=false;
  clearPrivate(); $("login-panel").hidden=false;
  const {error}=await sdk.auth.signOut({scope:"local"});
  if(error) throw new Error(error.message);
  status("已退出，私有页面数据已清除。");
}));
$("refresh").addEventListener("click",()=>action(showSession));
$("search").addEventListener("input",renderList);
$("password-form").addEventListener("submit",event=>{
  event.preventDefault(); action(async()=>{
    const {error}=await sdk.auth.updateUser({password:$("new-password").value});
    $("new-password").value=""; if(error) throw new Error(error.message);
    passwordRecovery=false;
    status("账号密码已更新。");
  });
});
$("enroll-mfa").addEventListener("click",()=>action(async()=>{
  const {data,error}=await sdk.auth.mfa.enroll({factorType:"totp",friendlyName:"AgentMatrix admin"});
  if(error) throw new Error(error.message);
  $("mfa-secret").hidden=false;
  $("mfa-secret").textContent=`在验证器手动添加此TOTP密钥，验证后不再显示：\n${data.totp.secret}`;
  const option=text("option","新验证器"); option.value=data.id; $("mfa-factor").append(option);
  $("mfa-factor").value=data.id;
  status("验证器密钥已生成。请在手机验证器中添加密钥，再输入当前六位验证码完成绑定。");
}));
$("mfa-form").addEventListener("submit",event=>{
  event.preventDefault(); action(async()=>{
    const factorId=$("mfa-factor").value;
    const challenge=await sdk.auth.mfa.challenge({factorId});
    if(challenge.error) throw new Error(challenge.error.message);
    const verified=await sdk.auth.mfa.verify({factorId,challengeId:challenge.data.id,code:$("mfa-code").value});
    $("mfa-code").value="";
    if(verified.error) throw new Error(verified.error.code==="mfa_verification_failed" ?
      "验证码不正确或已过期，请确认手机时间自动同步，再输入验证器当前的六位数字。" : verified.error.message);
    $("mfa-secret").textContent=""; $("mfa-secret").hidden=true;
    await showSession();
  });
});
$("draft-form").addEventListener("submit",event=>{
  event.preventDefault(); action(async()=>{
    const payload=payloadFromForm();
    const saved=selected?.state==="draft" && selected.owner_id===currentUser.id ?
      await api.update(selected.id,payload) : await api.create(payload);
    await reload(saved.id); status(`私有草稿已保存，ID ${saved.id}。尚未提交审核。`);
  });
});
$("new-draft").addEventListener("click",()=>{
  const previousVersion=Number($("version").value) || 0;
  selected=null; files=[]; downloaded.clear(); $("version").value=previousVersion+1;
  $("save-draft").textContent="保存新版本草稿";
  $("selected-label").textContent="保存后才会创建新版本，不覆盖旧提交。";
  $("submission-detail").textContent=""; $("file-list").replaceChildren(); $("review-history").textContent="";
  $("review-panel").hidden=true;
});
$("import-manifest").addEventListener("change",()=>action(async()=>{
  const file=$("import-manifest").files[0]; if(!file) return;
  if(file.size>262144) throw new Error("草稿包最大256KB");
  const value=JSON.parse(await file.text());
  if(value.status!=="prepared_not_submitted") throw new Error("只接受本地准备的草稿包");
  const keys=["factor_id","version","title","formula","license","code_hash","config_hash","data_hash","metrics","blockers","verification_stage"];
  const payload=draftPayload(Object.fromEntries(keys.map(k=>[k,value[k]])));
  selected=null; files=[]; downloaded.clear(); fillForm(payload);
  $("save-draft").textContent="保存新草稿"; $("submission-detail").textContent="";
  $("selected-label").textContent="本地草稿已导入，尚未写入线上。";
  $("file-list").replaceChildren(); $("review-history").textContent=""; $("review-panel").hidden=true;
  status("草稿已导入；核实附件许可后保存，并上传实际证据。");
}));
$("upload").addEventListener("click",()=>action(async()=>{
  if(!selected || selected.state!=="draft" || selected.owner_id!==currentUser.id) throw new Error("请选择本人的草稿");
  const uploadFiles=[...$("upload-files").files];
  if(!uploadFiles.length) throw new Error("请选择附件");
  let bytes=files.reduce((sum,f)=>sum+Number(f.size_bytes),0);
  for(const file of uploadFiles) {
    const pending=files.find(f=>f.name===file.name && f.status==="reserved");
    if(pending) {
      validateFile(file,0);
      await api.finishUpload(pending,file);
    } else {
      validateFile(file,bytes); await api.upload(selected.id,file,bytes); bytes+=file.size;
    }
  }
  await reload(selected.id); $("upload-files").value="";
  status("已上传至私有桶，内容仍待人工检查，不会自动执行。");
}));
$("submit").addEventListener("click",()=>action(async()=>{
  if(!selected) throw new Error("请选择本人的草稿");
  const receipt=await api.submit(selected.id);
  await reload(receipt.id);
  status(`真实提交回执：${receipt.id}\n状态：${STATES[receipt.state]}\n冻结指纹：${receipt.frozen_hash}`);
}));
$("begin-review").addEventListener("click",()=>action(async()=>{
  if(!selected) throw new Error("请选择提交");
  const row=await api.beginReview(selected.id); await reload(row.id);
  status("已领取独立审核，先下载并人工检查附件。");
}));
$("review").addEventListener("click",()=>action(async()=>{
  if(!selected) throw new Error("请选择提交");
  const receipt=await api.review(selected.id,$("decision").value,$("review-note").value,JSON.parse($("attestation").value));
  await reload(receipt.id); status(`审核已保存：${STATES[receipt.state]}。不自动公开。`);
}));

await action(async()=>{
  if (window.PRIVATE_FACTOR_BACKEND_ENABLED === false) {
    clearPrivate();
    $("login-panel").hidden=true;
    status("此入口的私有后端尚未开通，当前不能登录或上传。请使用服务器私有工作区备用入口。");
    return;
  }
  if(!window.supabase || !window.FACTOR_LAB_SUPABASE_URL || !window.FACTOR_LAB_SUPABASE_ANON_KEY) {
    throw new Error("Supabase SDK或公开项目配置不可用");
  }
  sdk=window.supabase.createClient(window.FACTOR_LAB_SUPABASE_URL,window.FACTOR_LAB_SUPABASE_ANON_KEY,{
    auth:{storage:window.sessionStorage,persistSession:true,autoRefreshToken:true,detectSessionInUrl:true},
    global:{fetch:(url,options)=>fetch(url,{...options,cache:"no-store"})}
  });
  api=new PrivateFactorClient(sdk);
  sdk.auth.onAuthStateChange(event=>{
    if(event==="SIGNED_OUT") { clearPrivate(); $("login-panel").hidden=false; status("会话已退出。"); }
    // Initial load and the login handler each await showSession themselves.
    // Re-entering it on SIGNED_IN races those calls and overwrites their result.
    // Recovery is raised during SDK initialization, before getUser resolves.
    if(event==="PASSWORD_RECOVERY") passwordRecovery=true;
  });
  await showSession();
});
