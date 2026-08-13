// Mock 实现：包装 data/mock.ts，模拟后端接口行为（含网络延迟）
// 后端就绪后此文件不再被引用（USE_MOCK=false）
import {
  BENCHMARKS,
  STRATEGIES,
  benchmarkSeries,
  computeWindow,
  dates,
  strategyDataMap,
} from "@/data/mock";
import type {
  ApiKpis,
  ApiNavPoint,
  ApiStrategySummary,
  BacktestJob,
  BacktestSubmitRequest,
  PortfolioBacktestRequest,
  PortfolioBacktestResult,
  PositionOverview,
  RiskAlert,
  RiskOverview,
  DrawdownEvent,
  TradePage,
  TradeQuery,
  TradeRow,
  UploadStrategyResponse,
} from "./types";

const delay = (ms = 260) => new Promise<void>((r) => setTimeout(r, ms));

/* ---------- 策略 ---------- */
export async function listStrategies(): Promise<ApiStrategySummary[]> {
  await delay(120);
  return STRATEGIES.map((def) => {
    const { stats } = computeWindow(def.id, "csi300", "全部");
    return {
      id: def.id,
      name: def.name,
      tag: def.tag,
      status: def.status,
      version: def.version,
      annualReturn: stats.annual,
      sharpe: stats.sharpe,
      todayReturn: strategyDataMap[def.id].today,
    };
  });
}

/* ---------- 上传策略 ---------- */
export async function uploadStrategy(file: File): Promise<UploadStrategyResponse> {
  await delay(700);
  const ok = file.name.endsWith(".py");
  return {
    fileId: `file_${Date.now().toString(36)}`,
    name: file.name,
    size: file.size,
    parsedOk: ok,
    message: ok ? "解析通过：检测到 init / handle_bar 入口函数" : "解析失败：仅支持 .py 策略文件",
  };
}

/* ---------- 回测任务 ---------- */
export const INITIAL_JOBS: BacktestJob[] = [
  { id: "BT-260728-014", strategyName: "动量轮动增强", status: "done", progress: 100, submittedAt: "2026-07-28 16:02", durationMs: 214000, resultId: "R-014" },
  { id: "BT-260728-013", strategyName: "阿尔法混合多策略", status: "running", progress: 67, submittedAt: "2026-07-28 15:41" },
  { id: "BT-260728-012", strategyName: "高频网格_v3", status: "queued", progress: 0, submittedAt: "2026-07-28 15:37" },
  { id: "BT-260727-011", strategyName: "CTA 趋势跟踪", status: "failed", progress: 42, submittedAt: "2026-07-27 20:15", error: "数据缺失：rb2610 合约分钟线不完整" },
  { id: "BT-260727-010", strategyName: "中性套利一号", status: "done", progress: 100, submittedAt: "2026-07-27 18:03", durationMs: 158000, resultId: "R-010" },
];

export async function listJobs(): Promise<BacktestJob[]> {
  await delay(150);
  return INITIAL_JOBS;
}

export async function submitBacktest(req: BacktestSubmitRequest): Promise<{ jobId: string }> {
  await delay(300);
  void req;
  return { jobId: `BT-260729-${Math.floor(Math.random() * 900 + 100)}` };
}

/* ---------- 组合回测（加权复合净值） ---------- */
function calcKpis(nav: number[], rets: number[]): ApiKpis {
  const n = nav.length;
  const total = nav[n - 1] - 1;
  const annual = Math.pow(nav[n - 1], 252 / n) - 1;
  const mean = rets.reduce((a, c) => a + c, 0) / n;
  const std = Math.sqrt(rets.reduce((a, c) => a + (c - mean) ** 2, 0) / n);
  const vol = std * Math.sqrt(252);
  let peak = 1;
  let maxDd = 0;
  nav.forEach((v) => {
    peak = Math.max(peak, v);
    maxDd = Math.min(maxDd, v / peak - 1);
  });
  return {
    totalReturn: total,
    annualReturn: annual,
    sharpe: (mean * 252 - 0.02) / vol,
    maxDrawdown: maxDd,
    winRate: rets.filter((r) => r > 0).length / n,
    volatility: vol,
  };
}

export async function runPortfolioBacktest(
  req: PortfolioBacktestRequest
): Promise<PortfolioBacktestResult> {
  await delay(900);
  const n = dates.length;
  const bench = benchmarkSeries.csi300;
  const retMatrix = req.items.map((it) => {
    const src = strategyDataMap[it.strategyId].nav;
    return src.map((v, i) => (i === 0 ? 0 : v / src[i - 1] - 1));
  });
  let nav = 1;
  let peak = 1;
  const navArr: number[] = [];
  const retArr: number[] = [];
  const points: ApiNavPoint[] = dates.map((d, i) => {
    const r = req.items.reduce((a, it, k) => a + it.weight * retMatrix[k][i], 0);
    nav *= 1 + r;
    peak = Math.max(peak, nav);
    navArr.push(nav);
    retArr.push(r);
    return { date: d, nav, benchmark: bench[i], drawdown: nav / peak - 1 };
  });
  return {
    kpis: calcKpis(navArr, retArr),
    nav: points,
    weights: req.items,
  };
}

/* ---------- 交易记录 ---------- */
export async function listTrades(query: TradeQuery): Promise<TradePage> {
  await delay(150);
  const all: TradeRow[] = strategyDataMap[query.strategyId ?? STRATEGIES[0].id].trades;
  let rows = all;
  if (query.side) rows = rows.filter((t) => t.side === query.side);
  if (query.q) {
    const q = query.q.trim().toLowerCase();
    rows = rows.filter((t) => t.code.includes(q) || t.name.toLowerCase().includes(q));
  }
  const page = query.page ?? 1;
  const pageSize = query.pageSize ?? 10;
  return {
    total: rows.length,
    page,
    pageSize,
    rows: rows.slice((page - 1) * pageSize, page * pageSize),
  };
}

/* ---------- 持仓分析 ---------- */
export async function getPositions(strategyId: string): Promise<PositionOverview> {
  await delay(150);
  const def = STRATEGIES.find((s) => s.id === strategyId) ?? STRATEGIES[0];
  const holdings = strategyDataMap[def.id].holdings;
  const indMap = new Map<string, number>();
  const capMap = new Map<string, number>();
  holdings.forEach((h) => {
    indMap.set(h.industry, (indMap.get(h.industry) ?? 0) + h.weight);
    capMap.set(h.capStyle, (capMap.get(h.capStyle) ?? 0) + h.weight);
  });
  const sorted = [...holdings].sort((a, b) => b.weight - a.weight);
  return {
    count: holdings.length,
    totalWeight: def.positionRatio,
    top5Weight: sorted.slice(0, 5).reduce((a, c) => a + c.weight, 0),
    hhi: holdings.reduce((a, c) => a + c.weight * c.weight, 0),
    industries: [...indMap.entries()]
      .map(([name, weight]) => ({ name, weight }))
      .sort((a, b) => b.weight - a.weight),
    marketCap: ["大盘", "中盘", "小盘"].map((label) => ({
      label,
      weight: capMap.get(label) ?? 0,
    })),
    rows: holdings.map((h) => ({ ...h })),
  };
}

/* ---------- 风险监控 ---------- */
function detectDrawdownEvents(nav: number[], threshold = -0.05): DrawdownEvent[] {
  const events: DrawdownEvent[] = [];
  let peak = nav[0];
  let peakIdx = 0;
  let inEvent = false;
  let startIdx = 0;
  let trough = 0;
  let troughIdx = 0;
  for (let i = 1; i < nav.length; i += 1) {
    if (nav[i] >= peak) {
      if (inEvent) {
        events.push({
          start: dates[startIdx],
          trough: dates[troughIdx],
          recovered: dates[i],
          depth: trough,
          durationDays: i - startIdx,
        });
        inEvent = false;
      }
      peak = nav[i];
      peakIdx = i;
    } else {
      const dd = nav[i] / peak - 1;
      if (!inEvent && dd <= threshold) {
        inEvent = true;
        startIdx = peakIdx;
        trough = dd;
        troughIdx = i;
      } else if (inEvent && dd < trough) {
        trough = dd;
        troughIdx = i;
      }
    }
  }
  if (inEvent) {
    events.push({
      start: dates[startIdx],
      trough: dates[troughIdx],
      recovered: null,
      depth: trough,
      durationDays: nav.length - 1 - startIdx,
    });
  }
  return events.sort((a, b) => a.depth - b.depth).slice(0, 6);
}

function calcMonthlyReturns(nav: number[]): { month: string; ret: number }[] {
  const out: { month: string; ret: number }[] = [];
  let prevMonth = dates[0].slice(0, 7);
  let startNav = 1;
  for (let i = 0; i < nav.length; i += 1) {
    const m = dates[i].slice(0, 7);
    const isLast = i === nav.length - 1;
    if (m !== prevMonth || isLast) {
      out.push({ month: prevMonth, ret: nav[i - (m !== prevMonth ? 1 : 0)] / startNav - 1 });
      prevMonth = m;
      startNav = nav[i - (m !== prevMonth ? 1 : 0)];
    }
  }
  return out;
}

export async function getRiskOverview(strategyId: string): Promise<RiskOverview> {
  await delay(150);
  const def = STRATEGIES.find((s) => s.id === strategyId) ?? STRATEGIES[0];
  const nav = strategyDataMap[def.id].nav;
  const { stats } = computeWindow(def.id, "csi300", "全部");
  const holdings = strategyDataMap[def.id].holdings;
  const maxHold = Math.max(...holdings.map((h) => h.weight));
  const minRet = Math.min(
    ...nav.map((v, i) => (i === 0 ? 0 : v / nav[i - 1] - 1))
  );
  const alerts: RiskAlert[] = [
    { id: "dd", rule: "最大回撤超限", threshold: "≤ -15%", current: `${(stats.maxDd * 100).toFixed(1)}%`, triggered: stats.maxDd <= -0.15, enabled: true },
    { id: "vol", rule: "年化波动率超限", threshold: "≥ 25%", current: `${(stats.vol * 100).toFixed(1)}%`, triggered: stats.vol >= 0.25, enabled: true },
    { id: "day", rule: "单日亏损超限", threshold: "≤ -3%", current: `${(minRet * 100).toFixed(1)}%`, triggered: minRet <= -0.03, enabled: true },
    { id: "hold", rule: "单票仓位超限", threshold: "≥ 25%", current: `${(maxHold * 100).toFixed(1)}%`, triggered: maxHold >= 0.25, enabled: true },
    { id: "lev", rule: "杠杆率超限", threshold: "≥ 2.0x", current: `${def.leverage.toFixed(1)}x`, triggered: def.leverage >= 2.0, enabled: false },
  ];
  return {
    currentDrawdown: strategyDataMap[def.id].nav[nav.length - 1] / Math.max(...nav) - 1,
    var95: stats.var95,
    volatility: stats.vol,
    beta: 0.72,
    leverage: def.leverage,
    alerts,
    drawdownEvents: detectDrawdownEvents(nav),
    monthlyReturns: calcMonthlyReturns(nav),
  };
}

/* ---------- 预设组合 ---------- */
export const PRESET_PORTFOLIOS: {
  name: string;
  desc: string;
  items: { strategyId: string; weight: number }[];
}[] = [
  {
    name: "均衡多策略",
    desc: "主策略打底，套利对冲平滑波动",
    items: [
      { strategyId: "alpha", weight: 0.5 },
      { strategyId: "arb", weight: 0.3 },
      { strategyId: "cta", weight: 0.2 },
    ],
  },
  {
    name: "进取轮动",
    desc: "股票多头为主，追求超额弹性",
    items: [
      { strategyId: "mom", weight: 0.6 },
      { strategyId: "alpha", weight: 0.4 },
    ],
  },
];

export { BENCHMARKS };
