// Mock 数据层：种子随机，保证刷新后数据可复现
// 支持多策略、多基准，所有统计指标统一从净值序列推导
function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function fmtDate(d: Date): string {
  const m = `${d.getMonth() + 1}`.padStart(2, "0");
  const day = `${d.getDate()}`.padStart(2, "0");
  return `${d.getFullYear()}-${m}-${day}`;
}

function pct(x: number, digits = 2): string {
  return `${x >= 0 ? "+" : ""}${(x * 100).toFixed(digits)}%`;
}

/* ---------- 交易日序列 ---------- */
export const dates: string[] = (() => {
  const arr: string[] = [];
  const d = new Date(2025, 7, 1);
  const end = new Date(2026, 6, 28);
  while (d <= end) {
    const day = d.getDay();
    if (day !== 0 && day !== 6) arr.push(fmtDate(d));
    d.setDate(d.getDate() + 1);
  }
  return arr;
})();

/* ---------- 基准指数 ---------- */
export interface BenchmarkDef {
  key: string;
  name: string;
}

export const BENCHMARKS: BenchmarkDef[] = [
  { key: "csi300", name: "沪深300" },
  { key: "csi500", name: "中证500" },
  { key: "csi1000", name: "中证1000" },
];

export const benchmarkSeries: Record<string, number[]> = (() => {
  const defs: [string, number, number][] = [
    ["csi300", 0.0002, 0.024],
    ["csi500", 0.00035, 0.03],
    ["csi1000", 0.00045, 0.036],
  ];
  const map: Record<string, number[]> = {};
  defs.forEach(([key, drift, amp], di) => {
    const r = mulberry32(9100 + di * 77);
    let v = 1;
    map[key] = dates.map(() => {
      v *= 1 + drift + (r() - 0.5) * amp;
      return v;
    });
  });
  return map;
})();

/* ---------- 策略定义 ---------- */
export interface StrategyDef {
  id: string;
  name: string;
  tag: string;
  status: "running" | "paused";
  version: string;
  positionRatio: number; // 总仓位
  leverage: number; // 杠杆率
  drift: number; // 日常漂移
  amp: number; // 日波动幅度
  corrDrift: number; // 回调段漂移
  corrWindow: [number, number]; // 回调区间（交易日索引）
  seed: number;
}

export const STRATEGIES: StrategyDef[] = [
  { id: "alpha", name: "阿尔法混合多策略", tag: "多策略", status: "running", version: "v2.4.1", positionRatio: 0.92, leverage: 1.0, drift: 0.0018, amp: 0.038, corrDrift: -0.0035, corrWindow: [118, 141], seed: 20260729 },
  { id: "mom", name: "动量轮动增强", tag: "股票多头", status: "running", version: "v1.9.0", positionRatio: 0.95, leverage: 1.2, drift: 0.0021, amp: 0.05, corrDrift: -0.006, corrWindow: [95, 130], seed: 20260730 },
  { id: "cta", name: "CTA 趋势跟踪", tag: "期货", status: "paused", version: "v3.1.2", positionRatio: 0.6, leverage: 1.8, drift: 0.0009, amp: 0.028, corrDrift: -0.0028, corrWindow: [150, 175], seed: 20260731 },
  { id: "arb", name: "中性套利一号", tag: "市场中性", status: "running", version: "v1.2.7", positionRatio: 0.85, leverage: 1.0, drift: 0.0008, amp: 0.012, corrDrift: -0.0012, corrWindow: [100, 112], seed: 20260732 },
];

/* ---------- 持仓 / 交易 / 子策略 ---------- */
export interface Holding {
  code: string;
  name: string;
  industry: string;
  capStyle: "大盘" | "中盘" | "小盘";
  qty: number;
  cost: number;
  price: number;
  value: number;
  pnl: number;
  pnlPct: number;
  weight: number;
}

export interface Trade {
  time: string;
  code: string;
  name: string;
  side: "buy" | "sell";
  price: number;
  qty: number;
  amount: number;
  fee: number;
}

export interface SubStrategy {
  name: string;
  weight: number;
  contribution: number;
  color: string;
}

const STOCKS: [string, string, string, "大盘" | "中盘" | "小盘"][] = [
  ["600519", "贵州茅台", "食品饮料", "大盘"],
  ["300750", "宁德时代", "电力设备", "大盘"],
  ["600036", "招商银行", "银行", "大盘"],
  ["601318", "中国平安", "非银金融", "大盘"],
  ["002594", "比亚迪", "汽车", "大盘"],
  ["688981", "中芯国际", "电子", "中盘"],
  ["603259", "药明康德", "医药生物", "中盘"],
  ["002475", "立讯精密", "电子", "中盘"],
  ["601899", "紫金矿业", "有色金属", "中盘"],
  ["600900", "长江电力", "公用事业", "大盘"],
  ["002230", "科大讯飞", "计算机", "小盘"],
  ["300274", "阳光电源", "电力设备", "小盘"],
];

const SUB_COLORS = ["#22D3EE", "#67E8F9", "#0E7490", "#94A3B8", "#475569"];

const SUB_DEFS: Record<string, [string, number, number][]> = {
  alpha: [
    ["动量轮动", 0.32, 0.286],
    ["均值回复", 0.24, 0.192],
    ["CTA 趋势", 0.18, 0.221],
    ["套利对冲", 0.14, 0.098],
    ["现金管理", 0.12, 0.031],
  ],
  mom: [
    ["动量因子", 0.45, 0.312],
    ["质量因子", 0.28, 0.165],
    ["低波因子", 0.17, 0.074],
    ["现金管理", 0.1, 0.02],
  ],
  cta: [
    ["趋势跟踪", 0.5, 0.238],
    ["期限结构", 0.25, 0.095],
    ["跨品种套利", 0.15, 0.062],
    ["现金管理", 0.1, 0.018],
  ],
  arb: [
    ["期现套利", 0.4, 0.121],
    ["跨期套利", 0.35, 0.104],
    ["ETF 套利", 0.15, 0.043],
    ["现金管理", 0.1, 0.015],
  ],
};

function genHoldings(r: () => number): Holding[] {
  const pool = [...STOCKS];
  for (let i = pool.length - 1; i > 0; i -= 1) {
    const j = Math.floor(r() * (i + 1));
    [pool[i], pool[j]] = [pool[j], pool[i]];
  }
  const rows = pool.slice(0, 8).map(([code, name, industry, capStyle]) => {
    const qty = Math.floor(r() * 490 + 10) * 100;
    const price = 8 + r() * 400;
    const pnlPct = (r() - 0.38) * 0.5;
    const cost = price / (1 + pnlPct);
    const value = price * qty;
    return { code, name, industry, capStyle, qty, cost, price, value, pnl: value - cost * qty, pnlPct, weight: 0 };
  });
  const totalValue = rows.reduce((a, c) => a + c.value, 0);
  rows.forEach((x) => {
    x.weight = x.value / totalValue;
  });
  return rows.sort((a, b) => b.value - a.value);
}

function genTrades(r: () => number): Trade[] {
  const rows: Trade[] = [];
  const d = new Date(2026, 6, 28, 14, 55, 0);
  for (let i = 0; i < 42; i += 1) {
    const [code, name] = STOCKS[Math.floor(r() * STOCKS.length)];
    const side = r() > 0.45 ? "buy" : "sell";
    const price = 8 + r() * 400;
    const qty = Math.floor(r() * 90 + 10) * 100;
    const amount = price * qty;
    rows.push({
      time: `${fmtDate(d)} ${`${d.getHours()}`.padStart(2, "0")}:${`${d.getMinutes()}`.padStart(2, "0")}`,
      code,
      name,
      side,
      price,
      qty,
      amount,
      fee: amount * 0.00025,
    });
    d.setDate(d.getDate() - (r() > 0.6 ? 1 : 0));
    d.setHours(9 + Math.floor(r() * 5), Math.floor(r() * 60), 0);
    if (d.getDay() === 0) d.setDate(d.getDate() - 2);
    if (d.getDay() === 6) d.setDate(d.getDate() - 1);
  }
  return rows;
}

/* ---------- 每个策略的完整数据包 ---------- */
export interface StrategyData {
  nav: number[];
  holdings: Holding[];
  trades: Trade[];
  subStrategies: SubStrategy[];
  today: number;
  spark: number[];
}

export const strategyDataMap: Record<string, StrategyData> = (() => {
  const map: Record<string, StrategyData> = {};
  STRATEGIES.forEach((def) => {
    const r = mulberry32(def.seed);
    const nav: number[] = [];
    let s = 1;
    dates.forEach((_, i) => {
      const inCorr = i >= def.corrWindow[0] && i <= def.corrWindow[1];
      s *= 1 + (inCorr ? def.corrDrift : def.drift) + (r() - 0.5) * def.amp;
      nav.push(s);
    });
    const n = nav.length;
    map[def.id] = {
      nav,
      holdings: genHoldings(r),
      trades: genTrades(r),
      subStrategies: SUB_DEFS[def.id].map(([name, weight, contribution], i) => ({
        name,
        weight,
        contribution,
        color: SUB_COLORS[i % SUB_COLORS.length],
      })),
      today: nav[n - 1] / nav[n - 2] - 1,
      spark: nav.slice(-22),
    };
  });
  return map;
})();

/* ---------- 区间切片 ---------- */
export const PERIODS = ["1M", "3M", "6M", "YTD", "1Y", "全部"] as const;

export function sliceForPeriod(period: string): [number, number] {
  const n = dates.length;
  switch (period) {
    case "1M":
      return [Math.max(0, n - 21), n];
    case "3M":
      return [Math.max(0, n - 63), n];
    case "6M":
      return [Math.max(0, n - 126), n];
    case "YTD": {
      const idx = dates.findIndex((d) => d >= "2026-01-01");
      return [idx === -1 ? 0 : idx, n];
    }
    default:
      return [0, n];
  }
}

/* ---------- 窗口数据与统计推导 ---------- */
export interface NavPoint {
  date: string;
  strategy: number;
  benchmark: number;
  drawdown: number;
  ret: number;
}

export interface Stats {
  total: number;
  annual: number;
  sharpe: number;
  sortino: number;
  calmar: number;
  maxDd: number;
  maxDdDate: string;
  winRate: number;
  vol: number;
  downVol: number;
  var95: number;
  benchTotal: number;
}

export interface Kpi {
  key: string;
  label: string;
  value: string;
  sub: string;
  tone: "up" | "down" | "accent";
}

export interface MetricItem {
  label: string;
  value: string;
  tone?: "up" | "down" | "flat";
}
export interface MetricGroup {
  title: string;
  en: string;
  items: MetricItem[];
}

export interface WindowData {
  points: NavPoint[];
  stats: Stats;
  kpis: Kpi[];
  metricGroups: MetricGroup[];
}

function computeStats(points: NavPoint[]): Stats {
  const n = points.length;
  const last = points[n - 1];
  const total = last.strategy - 1;
  const annual = Math.pow(last.strategy, 252 / n) - 1;
  const rets = points.map((p) => p.ret);
  const mean = rets.reduce((a, c) => a + c, 0) / n;
  const std = Math.sqrt(rets.reduce((a, c) => a + (c - mean) ** 2, 0) / n);
  const dStd = Math.sqrt(rets.filter((r) => r < 0).reduce((a, c) => a + c * c, 0) / n);
  const vol = std * Math.sqrt(252);
  const downVol = dStd * Math.sqrt(252);
  const maxPoint = points.reduce((m, p) => (p.drawdown < m.drawdown ? p : m), points[0]);
  return {
    total,
    annual,
    sharpe: (mean * 252 - 0.02) / vol,
    sortino: (mean * 252 - 0.02) / downVol,
    calmar: annual / Math.max(Math.abs(maxPoint.drawdown), 0.0001),
    maxDd: maxPoint.drawdown,
    maxDdDate: maxPoint.date,
    winRate: rets.filter((r) => r > 0).length / n,
    vol,
    downVol,
    var95: -1.645 * std,
    benchTotal: last.benchmark - 1,
  };
}

export function computeWindow(strategyId: string, benchmarkKey: string, period: string): WindowData {
  const sd = strategyDataMap[strategyId] ?? strategyDataMap[STRATEGIES[0].id];
  const bench = benchmarkSeries[benchmarkKey] ?? benchmarkSeries[BENCHMARKS[0].key];
  const [s, e] = sliceForPeriod(period);
  const baseS = sd.nav[s];
  const baseB = bench[s];
  let peak = -Infinity;
  const points: NavPoint[] = [];
  for (let i = s; i < e; i += 1) {
    const sv = sd.nav[i] / baseS;
    peak = Math.max(peak, sv);
    points.push({
      date: dates[i],
      strategy: sv,
      benchmark: bench[i] / baseB,
      drawdown: sv / peak - 1,
      ret: i === 0 ? 0 : sd.nav[i] / sd.nav[i - 1] - 1,
    });
  }
  const stats = computeStats(points);

  const kpis: Kpi[] = [
    { key: "total", label: "累计收益率", value: pct(stats.total), sub: `基准 ${pct(stats.benchTotal)}`, tone: stats.total >= 0 ? "up" : "down" },
    { key: "annual", label: "年化收益率", value: pct(stats.annual), sub: "区间年化", tone: stats.annual >= 0 ? "up" : "down" },
    { key: "sharpe", label: "夏普比率", value: stats.sharpe.toFixed(2), sub: "无风险利率 2.0%", tone: "accent" },
    { key: "maxdd", label: "最大回撤", value: pct(stats.maxDd), sub: `${stats.maxDdDate} 见底`, tone: "down" },
    { key: "win", label: "日胜率", value: `${(stats.winRate * 100).toFixed(1)}%`, sub: "盈亏比 1.62", tone: "accent" },
    { key: "vol", label: "年化波动率", value: `${(stats.vol * 100).toFixed(1)}%`, sub: `下行波动 ${(stats.downVol * 100).toFixed(1)}%`, tone: "accent" },
  ];

  const metricGroups: MetricGroup[] = [
    {
      title: "收益指标",
      en: "RETURN",
      items: [
        { label: "累计收益", value: pct(stats.total), tone: stats.total >= 0 ? "up" : "down" },
        { label: "年化收益", value: pct(stats.annual), tone: stats.annual >= 0 ? "up" : "down" },
        { label: "月度胜率", value: "63.6%", tone: "flat" },
        { label: "盈亏比", value: "1.62", tone: "flat" },
        { label: "单周最佳", value: "+6.83%", tone: "up" },
      ],
    },
    {
      title: "风险指标",
      en: "RISK",
      items: [
        { label: "最大回撤", value: pct(stats.maxDd), tone: "down" },
        { label: "最长回撤修复", value: "38 天", tone: "flat" },
        { label: "年化波动率", value: `${(stats.vol * 100).toFixed(1)}%`, tone: "flat" },
        { label: "下行波动率", value: `${(stats.downVol * 100).toFixed(1)}%`, tone: "flat" },
        { label: "VaR (95%)", value: pct(stats.var95), tone: "down" },
      ],
    },
    {
      title: "风险调整",
      en: "ADJUSTED",
      items: [
        { label: "夏普比率", value: stats.sharpe.toFixed(2), tone: "flat" },
        { label: "索提诺比率", value: stats.sortino.toFixed(2), tone: "flat" },
        { label: "卡玛比率", value: stats.calmar.toFixed(2), tone: "flat" },
        { label: "信息比率", value: "1.12", tone: "flat" },
        { label: "贝塔(β)", value: "0.72", tone: "flat" },
      ],
    },
  ];

  return { points, stats, kpis, metricGroups };
}

/* ---------- 格式化工具 ---------- */
export function fmtMoney(v: number): string {
  if (Math.abs(v) >= 10000) return `${(v / 10000).toFixed(2)}万`;
  return v.toFixed(2);
}
