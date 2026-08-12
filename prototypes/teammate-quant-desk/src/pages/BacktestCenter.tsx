import { useEffect, useState } from "react";
import { Loader2, Play, RefreshCw, ShieldCheck } from "lucide-react";
import Card from "@/components/Card";
import { getBacktestCapabilities, listCanonicalJobs, submitCanonicalBacktest } from "@/api";
import type { BacktestCapabilities } from "@/api/types";
import { useDashStore } from "@/store/useDashStore";

const INPUT = "w-full rounded-lg border border-line bg-ink-900 px-3 py-2 text-xs text-fg outline-none focus:border-accent/50";
const LABELS: Record<string,string> = {queued:"排队中",running:"运行中",validating:"校验中",completed:"已完成",failed:"失败"};

export default function BacktestCenter() {
  const notify = useDashStore(s=>s.notify);
  const setStrategy = useDashStore(s=>s.setStrategy);
  const [caps,setCaps]=useState<BacktestCapabilities|null>(null);
  const [jobs,setJobs]=useState<any[]>([]);
  const [token,setToken]=useState("");
  const [strategy,setSelected]=useState("");
  const [start,setStart]=useState("2024-01-01");
  const [end,setEnd]=useState(new Date().toISOString().slice(0,10));
  const [capital,setCapital]=useState("1000000");
  const [rebalance,setRebalance]=useState("20");
  const [commission,setCommission]=useState("3");
  const [slippage,setSlippage]=useState("10");
  const [busy,setBusy]=useState(false);
  const load=()=>listCanonicalJobs().then(setJobs).catch(()=>setJobs([]));
  useEffect(()=>{getBacktestCapabilities().then(c=>{setCaps(c);setSelected(c.strategies[0]?.id||"")});load()},[]);
  useEffect(()=>{const active=jobs.some(j=>["queued","running","validating"].includes(j.status));if(!active)return;const t=setInterval(load,3000);return()=>clearInterval(t)},[jobs]);
  async function submit(e:React.FormEvent){e.preventDefault();setBusy(true);try{const j=await submitCanonicalBacktest({strategy_id:strategy,start_date:start,end_date:end,initial_cash:Number(capital),rebalance_freq:Number(rebalance),commission_bps:Number(commission),slippage_bps:Number(slippage)},token);notify(`真实回测已进入队列：${j.job_id}`);await load()}catch(e){notify(`提交失败：${e instanceof Error?e.message:"未知错误"}`)}finally{setBusy(false)}}
  return <main className="mx-auto max-w-[1600px] space-y-4 px-6 py-5">
    <div className="rounded-xl border border-down/20 bg-down/[0.04] px-5 py-4 text-xs text-fg-soft"><div className="flex items-center gap-2 font-semibold text-down"><ShieldCheck size={16}/>安全的真实回测入口</div><p className="mt-1.5 text-fg-mute">仅运行 AgentMatrix 注册策略。任务由持久队列保存并交给服务器晨曦 Worker；任意 Python 上传已关闭。</p></div>
    <div className="grid grid-cols-12 gap-4"><Card title="回测参数" en="CHENXI ENGINE" className="col-span-5" pad={false}><form onSubmit={submit} className="grid grid-cols-2 gap-4 p-5">
      <label className="col-span-2 text-[11px] text-fg-mute">访问令牌<input type="password" value={token} onChange={e=>setToken(e.target.value)} className={`${INPUT} mt-1.5`} placeholder="管理员提供，仅驻留当前页面"/></label>
      <label className="col-span-2 text-[11px] text-fg-mute">注册策略<select value={strategy} onChange={e=>setSelected(e.target.value)} className={`${INPUT} mt-1.5`}>{caps?.strategies.map(s=><option key={s.id} value={s.id}>{s.name} · {s.status}</option>)}</select></label>
      <label className="text-[11px] text-fg-mute">开始日期<input type="date" value={start} onChange={e=>setStart(e.target.value)} className={`${INPUT} mt-1.5`}/></label><label className="text-[11px] text-fg-mute">结束日期<input type="date" value={end} onChange={e=>setEnd(e.target.value)} className={`${INPUT} mt-1.5`}/></label>
      <label className="text-[11px] text-fg-mute">初始资金<input value={capital} onChange={e=>setCapital(e.target.value)} className={`${INPUT} mt-1.5`}/></label><label className="text-[11px] text-fg-mute">调仓频率<input value={rebalance} onChange={e=>setRebalance(e.target.value)} className={`${INPUT} mt-1.5`}/></label>
      <label className="text-[11px] text-fg-mute">佣金 bps<input value={commission} onChange={e=>setCommission(e.target.value)} className={`${INPUT} mt-1.5`}/></label><label className="text-[11px] text-fg-mute">滑点 bps<input value={slippage} onChange={e=>setSlippage(e.target.value)} className={`${INPUT} mt-1.5`}/></label>
      <button disabled={!caps?.submission_enabled||busy} className="col-span-2 flex items-center justify-center gap-2 rounded-lg bg-accent px-4 py-2.5 text-xs font-bold text-ink-950 disabled:opacity-40">{busy?<Loader2 size={14} className="animate-spin"/>:<Play size={14}/>}提交服务器真实回测</button>
    </form></Card><Card title="持久任务队列" en="DURABLE JOBS" className="col-span-7" pad={false} actions={<button onClick={load}><RefreshCw size={14}/></button>}><div className="max-h-[520px] divide-y divide-line/50 overflow-auto">{jobs.map(j=><div key={j.job_id} className="p-4"><div className="flex items-center"><strong className="text-xs text-fg">{j.request.strategy_id}</strong><span className="ml-2 rounded-full bg-ink-600 px-2 py-0.5 text-[10px] text-accent">{LABELS[j.status]||j.status}</span><small className="num ml-auto text-fg-mute">{j.progress}%</small></div><p className="num mt-1 text-[10px] text-fg-mute">{j.job_id} · {j.request.start_date} → {j.request.end_date}</p><div className="mt-2 h-1 overflow-hidden rounded bg-ink-600"><i className="block h-full bg-accent" style={{width:`${j.progress}%`}}/></div>{j.error&&<p className="mt-2 text-[10px] text-up">{j.error}</p>}{j.status==="completed"&&<button onClick={()=>{setStrategy(j.request.strategy_id);location.href="/quant-desk/"}} className="mt-2 text-[11px] text-accent">打开真实结果 →</button>}</div>)}{!jobs.length&&<div className="p-10 text-center text-xs text-fg-mute">暂无任务</div>}</div></Card></div>
  </main>;
}
