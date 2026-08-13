// 后端 API 契约类型 —— 与 .trae/documents/quant_dashboard_tech.md 第 4 节严格一致
// 后端实现方请以此文件为准

/* ---------- 通用 ---------- */
export type BenchmarkKey = "csi300" | "csi500" | "csi1000";

export interface ApiErrorBody {
  code: number;
  message: string;
}

/* ---------- 策略 ---------- */
export interface ApiStrategySummary {
  id: string;
  name: string;
  tag: string;
  status: "running" | "paused";
  version: string;
  annualReturn: number;
  sharpe: number;
  todayReturn: number;
  spark: number[];
}

/** 策略详情（含净值曲线、持仓、交易） */
export interface ApiStrategyDetail {
  id: string;
  name: string;
  tag: string;
  status: "running" | "paused";
  version: string;
  nav: ApiNavPoint[];
  kpis: ApiKpis;
  holdings: PositionRow[];
  trades: TradeRow[];
  subStrategies: { id: string; name: string; weight: number }[];
}

export interface ApiNavPoint {
  date: string;
  nav: number;
  benchmark: number;
  drawdown: number;
}

export interface ApiKpis {
  totalReturn: number;
  annualReturn: number;
  sharpe: number;
  maxDrawdown: number;
  winRate: number;
  volatility: number;
}

/* ---------- 上传策略 ---------- */
export interface UploadStrategyResponse {
  fileId: string;
  name: string;
  size: number;
  parsedOk: boolean;
  message: string;
}

/* ---------- 回测任务 ---------- */
export interface BacktestSubmitRequest {
  fileId?: string;
  strategyId?: string;
  start: string; // YYYY-MM-DD
  end: string; // YYYY-MM-DD
  capital: number;
  benchmark: BenchmarkKey;
  feeRate: number;
  slippage: number;
}

export type JobStatus = "queued" | "running" | "done" | "failed";

export interface BacktestJob {
  id: string;
  strategyName: string;
  status: JobStatus;
  progress: number; // 0-100
  submittedAt: string;
  durationMs?: number;
  resultId?: string;
  error?: string;
}

/* ---------- 组合回测 ---------- */
export interface PortfolioBacktestRequest {
  items: { strategyId: string; weight: number }[];
  rebalance: "weekly" | "monthly" | "quarterly";
  start: string;
  end: string;
}

export interface PortfolioBacktestResult {
  kpis: ApiKpis;
  nav: ApiNavPoint[];
  weights: { strategyId: string; weight: number }[];
}

/* ---------- 交易记录 ---------- */
export interface TradeRow {
  time: string;
  code: string;
  name: string;
  side: "buy" | "sell";
  price: number;
  qty: number;
  amount: number;
  fee: number;
}

export interface TradePage {
  total: number;
  page: number;
  pageSize: number;
  rows: TradeRow[];
}

export interface TradeQuery {
  strategyId?: string;
  side?: "buy" | "sell";
  q?: string;
  page?: number;
  pageSize?: number;
}

/* ---------- 持仓分析 ---------- */
export interface PositionRow {
  code: string;
  name: string;
  industry: string;
  qty: number;
  cost: number;
  price: number;
  value: number;
  pnl: number;
  pnlPct: number;
  weight: number;
}

export interface PositionOverview {
  count: number;
  totalWeight: number; // 总仓位
  top5Weight: number; // 前五大集中度
  hhi: number; // 赫芬达尔指数
  industries: { name: string; weight: number }[];
  marketCap: { label: string; weight: number }[];
  rows: PositionRow[];
}

/* ---------- 风险监控 ---------- */
export interface RiskAlert {
  id: string;
  rule: string;
  threshold: string;
  current: string;
  triggered: boolean;
  enabled: boolean;
}

export interface DrawdownEvent {
  start: string;
  trough: string;
  recovered: string | null;
  depth: number;
  durationDays: number;
}

export interface RiskOverview {
  currentDrawdown: number;
  var95: number;
  volatility: number;
  beta: number;
  leverage: number;
  alerts: RiskAlert[];
  drawdownEvents: DrawdownEvent[];
  monthlyReturns: { month: string; ret: number }[];
}

/* ---------- 策略总览（动态组合） ---------- */
export interface ApiOverviewFolio {
  id: string;
  name: string;
  tag: string;
  status: string;
  version: string;
  annualReturn: number;   // 小数, 如 0.1726
  totalReturn: number;    // 小数
  sharpe: number;
  maxDrawdown: number;    // 正数小数
  volatility: number;     // 小数
  todayReturn: number;
  spark: number[];
  weights: Record<string, number>;  // {strategyId: weight}
  navDates: string[];
  navValues: number[];              // 从 1.0 起算的归一化净值
}

export interface ApiOverviewResponse {
  folio: ApiOverviewFolio | null;
  strategies: ApiStrategySummary[];
}
