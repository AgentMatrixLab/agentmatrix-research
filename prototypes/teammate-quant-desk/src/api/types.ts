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
}

export interface CanonicalStrategySummary {
  id: string;
  name: string;
  version: string;
  engine: string;
  status: string;
  publication_status: string;
  quality_status: string;
  data_version?: string;
  start_date?: string;
  end_date?: string;
  total_return: number;
  annualized_return: number;
  sharpe: number;
  max_drawdown: number;
  updated_at?: string;
}

export interface CanonicalStrategyDetail extends CanonicalStrategySummary {
  benchmark?: string;
  metrics: Record<string, number | null>;
  equity_curve: { date: string; nav: number; benchmark: number; drawdown: number }[];
  positions: { symbol: string; weight: number }[];
  trades: { time: string; symbol: string; side: string; quantity: number; price: number; amount: number; commission: number; slippage: number }[];
  diagnostics: Record<string, unknown>;
}

export interface BacktestCapabilities {
  submission_enabled: boolean;
  strategies: { id: string; name: string; version: string; status: string }[];
  limits: Record<string, number>;
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
  var95: number | null;
  volatility: number;
  beta: number | null;
  leverage: number;
  alerts: RiskAlert[];
  drawdownEvents: DrawdownEvent[];
  monthlyReturns: { month: string; ret: number }[];
}
