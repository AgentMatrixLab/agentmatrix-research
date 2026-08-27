import type { CanonicalStrategyDetail, CanonicalStrategySummary } from "@/api/types";
import type { Holding, Kpi, MetricGroup, NavPoint, Stats, StrategyDef, Trade } from "@/data/mock";

export function liveDefinition(s: CanonicalStrategySummary): StrategyDef {
  return { id: s.id, name: s.name, tag: s.publication_status === "published" ? "已发布" : "研究验证", status: "running", version: s.version, positionRatio: 0, leverage: 1, drift: 0, amp: 0, corrDrift: 0, corrWindow: [0, 0], seed: 0 };
}

const pct = (v: number) => `${v >= 0 ? "+" : ""}${(v * 100).toFixed(2)}%`;

export function liveDashboard(detail: CanonicalStrategyDetail, period = "ALL") {
  const lengths: Record<string, number> = {"1M":21,"3M":63,"6M":126,"1Y":252,"3Y":756};
  let rows = detail.equity_curve;
  if (period === "YTD" && rows.length) rows = rows.filter(p => p.date.slice(0,4) === rows.at(-1)!.date.slice(0,4));
  else if (lengths[period]) rows = rows.slice(-lengths[period]);
  const baseNav = rows[0]?.nav || 1, baseBench = rows[0]?.benchmark || 1;
  const points: NavPoint[] = rows.map((p, i) => ({date: p.date, strategy: p.nav/baseNav, benchmark: p.benchmark/baseBench, drawdown: 0, ret: i ? p.nav / rows[i - 1].nav - 1 : 0}));
  let peak = 0; points.forEach(p => { peak=Math.max(peak,p.strategy); p.drawdown=p.strategy/peak-1; });
  const m = detail.metrics || {};
  const rets = points.map(p => p.ret).slice(1);
  const winRate = rets.length ? rets.filter(x => x > 0).length / rets.length : 0;
  const avg = rets.length ? rets.reduce((a,b)=>a+b,0)/rets.length : 0;
  const sigma = rets.length>1 ? Math.sqrt(rets.reduce((a,b)=>a+(b-avg)**2,0)/rets.length) : 0;
  const negatives = rets.filter(x=>x<0), downSigma = negatives.length ? Math.sqrt(negatives.reduce((a,b)=>a+b*b,0)/negatives.length) : 0;
  const total = points.length ? points.at(-1)!.strategy-1 : 0;
  const annual = rets.length && total>-1 ? (1+total)**(252/rets.length)-1 : 0;
  const maxDd = Math.abs(Math.min(0,...points.map(p=>p.drawdown)));
  const stats: Stats = {total, annual, sharpe:sigma?avg*Math.sqrt(252)/sigma:0, sortino:downSigma?avg*Math.sqrt(252)/downSigma:0, calmar:maxDd?annual/maxDd:0, maxDd, maxDdDate: points.reduce((a,b)=>b.drawdown<a.drawdown?b:a, points[0] || {date:"--",drawdown:0} as NavPoint).date, winRate, vol:sigma*Math.sqrt(252), downVol:downSigma*Math.sqrt(252), var95:avg-1.645*sigma, benchTotal:points.length ? points.at(-1)!.benchmark - 1 : 0};
  const kpis: Kpi[] = [
    {key:"total",label:"累计收益率",value:pct(stats.total),sub:`基准 ${pct(stats.benchTotal)}`,tone:stats.total>=0?"up":"down"},
    {key:"annual",label:"年化收益率",value:pct(stats.annual),sub:"晨曦引擎",tone:stats.annual>=0?"up":"down"},
    {key:"sharpe",label:"夏普比率",value:stats.sharpe.toFixed(2),sub:"真实回测",tone:"accent"},
    {key:"maxdd",label:"最大回撤",value:pct(stats.maxDd),sub:`${stats.maxDdDate} 见底`,tone:"down"},
    {key:"win",label:"日胜率",value:pct(stats.winRate),sub:"按净值日收益",tone:"accent"},
    {key:"vol",label:"年化波动率",value:pct(stats.vol),sub:"标准结果字段",tone:"accent"},
  ];
  const metricGroups: MetricGroup[] = [
    {title:"收益指标",en:"RETURN",items:[{label:"累计收益",value:pct(stats.total)},{label:"年化收益",value:pct(stats.annual)},{label:"超额收益",value:pct(m.excess_return||0)}]},
    {title:"风险指标",en:"RISK",items:[{label:"最大回撤",value:pct(stats.maxDd),tone:"down"},{label:"年化波动率",value:pct(stats.vol)},{label:"换手率",value:pct(m.turnover||0)}]},
    {title:"风险调整",en:"ADJUSTED",items:[{label:"夏普比率",value:stats.sharpe.toFixed(2)},{label:"索提诺比率",value:stats.sortino.toFixed(2)},{label:"卡玛比率",value:stats.calmar.toFixed(2)}]},
  ];
  const holdings: Holding[] = detail.positions.map((p: any) => ({code:p.symbol,name:p.name||p.symbol,industry:p.industry||"未提供",capStyle:p.market_cap>=50e9?"大盘":p.market_cap>=10e9?"中盘":"小盘",qty:p.quantity||0,cost:p.average_cost||0,price:p.last_price||0,value:p.market_value||0,pnl:p.unrealized_pnl||0,pnlPct:p.unrealized_pnl_pct||0,weight:p.weight}));
  const trades: Trade[] = detail.trades.map(t => ({time:t.time,code:t.symbol,name:t.symbol,side:t.side.toLowerCase()==="buy"?"buy":"sell",price:t.price,qty:t.quantity,amount:t.amount,fee:t.commission}));
  return {points,stats,kpis,metricGroups,holdings,trades,subStrategies:[]};
}
