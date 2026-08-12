import type { CanonicalStrategyDetail, CanonicalStrategySummary } from "@/api/types";
import type { Holding, Kpi, MetricGroup, NavPoint, Stats, StrategyDef, Trade } from "@/data/mock";

export function liveDefinition(s: CanonicalStrategySummary): StrategyDef {
  return { id: s.id, name: s.name, tag: s.publication_status === "published" ? "已发布" : "研究验证", status: "running", version: s.version, positionRatio: 0, leverage: 1, drift: 0, amp: 0, corrDrift: 0, corrWindow: [0, 0], seed: 0 };
}

const pct = (v: number) => `${v >= 0 ? "+" : ""}${(v * 100).toFixed(2)}%`;

export function liveDashboard(detail: CanonicalStrategyDetail) {
  const points: NavPoint[] = detail.equity_curve.map((p, i, rows) => ({date: p.date, strategy: p.nav, benchmark: p.benchmark, drawdown: p.drawdown, ret: i ? p.nav / rows[i - 1].nav - 1 : 0}));
  const m = detail.metrics || {};
  const rets = points.map(p => p.ret).slice(1);
  const winRate = rets.length ? rets.filter(x => x > 0).length / rets.length : 0;
  const stats: Stats = {total: m.total_return || 0, annual: m.annualized_return || 0, sharpe: m.sharpe || 0, sortino: m.sortino || 0, calmar: m.calmar || 0, maxDd: m.max_drawdown || 0, maxDdDate: points.reduce((a,b)=>b.drawdown<a.drawdown?b:a, points[0] || {date:"--",drawdown:0} as NavPoint).date, winRate, vol:m.volatility||0, downVol:m.downside_volatility||0, var95:m.var_95||0, benchTotal:points.length ? points.at(-1)!.benchmark - 1 : 0};
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
  const holdings: Holding[] = detail.positions.map(p => ({code:p.symbol,name:p.symbol,industry:"未提供",capStyle:"中盘",qty:0,cost:0,price:0,value:0,pnl:0,pnlPct:0,weight:p.weight}));
  const trades: Trade[] = detail.trades.map(t => ({time:t.time,code:t.symbol,name:t.symbol,side:t.side.toLowerCase()==="buy"?"buy":"sell",price:t.price,qty:t.quantity,amount:t.amount,fee:t.commission}));
  return {points,stats,kpis,metricGroups,holdings,trades,subStrategies:[]};
}
