// API 门面：页面只调用本文件；USE_MOCK 切换 Mock/真实后端，页面零改动
import { request, USE_MOCK } from "./client";
import * as mock from "./mockImpl";
import type {
  ApiStrategySummary,
  ApiStrategyDetail,
  BacktestJob,
  BacktestSubmitRequest,
  PortfolioBacktestRequest,
  PortfolioBacktestResult,
  PositionOverview,
  RiskOverview,
  TradePage,
  TradeQuery,
  UploadStrategyResponse,
  ApiOverviewResponse,
} from "./types";

export function listStrategies(): Promise<ApiStrategySummary[]> {
  return USE_MOCK ? mock.listStrategies() : request("/api/strategies");
}

export function getStrategyDetail(
  id: string,
  period = "all",
  benchmark = "csi300"
): Promise<ApiStrategyDetail> {
  return USE_MOCK
    ? mock.getStrategyDetail(id, period, benchmark)
    : request(`/api/strategies/${encodeURIComponent(id)}?period=${period}&benchmark=${benchmark}`);
}

export function uploadStrategy(file: File): Promise<UploadStrategyResponse> {
  if (USE_MOCK) return mock.uploadStrategy(file);
  const fd = new FormData();
  fd.append("file", file);
  return request("/api/strategies/upload", { method: "POST", body: fd });
}

export function submitBacktest(req: BacktestSubmitRequest): Promise<{ jobId: string }> {
  return USE_MOCK
    ? mock.submitBacktest(req)
    : request("/api/backtests", { method: "POST", body: JSON.stringify(req) });
}

export function listJobs(): Promise<BacktestJob[]> {
  return USE_MOCK ? mock.listJobs() : request("/api/backtests");
}

export function runPortfolioBacktest(
  req: PortfolioBacktestRequest
): Promise<PortfolioBacktestResult> {
  return USE_MOCK
    ? mock.runPortfolioBacktest(req)
    : request("/api/portfolio/backtest", { method: "POST", body: JSON.stringify(req) });
}

export function listTrades(query: TradeQuery): Promise<TradePage> {
  if (USE_MOCK) return mock.listTrades(query);
  const params = new URLSearchParams();
  Object.entries(query).forEach(([k, v]) => {
    if (v !== undefined && v !== "") params.set(k, String(v));
  });
  return request(`/api/trades?${params.toString()}`);
}

export function getPositions(strategyId: string): Promise<PositionOverview> {
  return USE_MOCK
    ? mock.getPositions(strategyId)
    : request(`/api/positions?strategyId=${encodeURIComponent(strategyId)}`);
}

export function getRiskOverview(strategyId: string): Promise<RiskOverview> {
  return USE_MOCK
    ? mock.getRiskOverview(strategyId)
    : request(`/api/risk/overview?strategyId=${encodeURIComponent(strategyId)}`);
}

export function getOverview(): Promise<ApiOverviewResponse> {
  return USE_MOCK ? mock.getOverview() : request("/api/overview");
}

export { PRESET_PORTFOLIOS } from "./mockImpl";
export * from "./types";
