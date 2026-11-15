"use strict";
(async()=>{
  const $=id=>document.getElementById(id);
  const cell=value=>{const n=document.createElement("td");n.textContent=value;return n;};
  const num=v=>Number(v).toFixed(4);
  const pct=v=>(Number(v)*100).toFixed(3)+"%";
  try {
    const response=await fetch("./data/turnover40-summary.json",{cache:"no-store"});
    if(!response.ok) throw new Error("真实摘要未加载");
    const r=await response.json();
    if(r.factor_id!=="JQGM:turnover_ratio_40d") throw new Error("证据身份不符");
    $("status").textContent=`评估从${r.evaluation_start}开始，数据截至${r.source_end}；线上私有回执：${r.online_submission_id || "尚未提交"}`;
    for(const [h,m] of Object.entries(r.horizons)){
      const row=document.createElement("tr");
      row.append(cell(h+"日"),cell(num(m.rank_ic)),cell(m.rank_ic_ci95.map(num).join(" ~ ")),
        cell(pct(m.low_minus_high)),cell(pct(m.q1_annualized_cost_proxy)));
      $("rows").append(row);
    }
    for(const value of r.limitations){const li=document.createElement("li");li.textContent=value;$("limits").append(li);}
    $("details").textContent=JSON.stringify(r,null,2);
  }catch(error){$("status").textContent="未能加载真实证据："+error.message;}
})();
