import { useEffect, useMemo, useState } from "react";
import { BENCHMARKS } from "@/data/mock";
import type { NavPoint, MetricGroup } from "@/data/mock";
import { useDashStore } from "@/store/useDashStore";
import { getStrategyDetail, type ApiStrategyDetail } from "@/api";

// 将 API 净值点转为 NavPoint（补 ret 字段）
function toPoints(nav: ApiStrategyDetail["nav"]): NavPoint[] {
  return nav.map((p, i) => ({
    date: p.date,
    strategy: p.nav,
    benchmark: p.benchmark,
    drawdown: p.drawdown,
    ret: i === 0 ? 0 : p.nav / nav[i - 1].nav - 1,
  }));
}

// 从净值序列算窗口统计
function computeStats(points: NavPoint[]) {
  const n = points.length;
  if (n < 2) return { total: 0, annual: 0, sharpe: 0, sortino: 0, calmar: 0, maxDd: 0, vol: 0, var95: 0, mar: 0 };
  const last = points[n - 1];
  const first = points[0];
  const total = last.strategy / first.strategy - 1;
  const years = Math.max(0.5, n / 252);
  const annual = Math.pow(last.strategy / first.strategy, 1 / years) - 1;
  const rets = points.slice(1).map((p, i) => p.strategy / points[i].strategy - 1);
  const meanRet = rets.reduce((a, c) => a + c, 0) / rets.length;
  const stdDaily = Math.sqrt(rets.reduce((a, c) => a + (c - meanRet) ** 2, 0) / rets.length);
  const vol = stdDaily * Math.sqrt(252);
  const sharpe = stdDaily > 0 ? (meanRet * 252 - 0.02) / vol : 0;

  const negRets = rets.filter((r) => r < 0);
  const sortinoStd = Math.sqrt(negRets.reduce((a, c) => a + c * c, 0) / (negRets.length || 1)) * Math.sqrt(252);
  const sortino = sortinoStd > 0 ? (meanRet * 252 - 0.02) / sortinoStd : 0;

  let peak = first.strategy;
  let maxDd = 0;
  points.forEach((p) => {
    peak = Math.max(peak, p.strategy);
    maxDd = Math.min(maxDd, p.strategy / peak - 1);
  });
  const calmar = Math.abs(maxDd) > 0 ? annual / Math.abs(maxDd) : 0;

  const sortedRets = [...rets].sort((a, b) => a - b);
  const var95 = sortedRets[Math.max(0, Math.floor(rets.length * 0.05))];

  return { total, annual, sharpe, sortino, calmar, maxDd, vol, var95, mar: annual / Math.abs(maxDd) };
}

// 构建 KPI 条
function buildKpis(detail: ApiStrategyDetail): any[] {
  const k = detail.kpis;
  return [
    { key: "totalReturn", label: "累计收益", value: `${(k.totalReturn * 100).toFixed(2)}%`, sub: "策略区间", tone: k.totalReturn >= 0 ? "up" : "down" },
    { key: "annualReturn", label: "年化收益", value: `${(k.annualReturn * 100).toFixed(2)}%`, sub: "年化复利", tone: k.annualReturn >= 0 ? "up" : "down" },
    { key: "sharpe", label: "夏普比率", value: k.sharpe.toFixed(3), sub: "风险调整收益", tone: k.sharpe >= 1 ? "up" : k.sharpe >= 0 ? "flat" : "down" },
    { key: "maxDrawdown", label: "最大回撤", value: `${(k.maxDrawdown * 100).toFixed(2)}%`, sub: "峰值到谷底", tone: k.maxDrawdown >= -0.1 ? "up" : k.maxDrawdown >= -0.2 ? "flat" : "down" },
    { key: "winRate", label: "胜率", value: `${(k.winRate * 100).toFixed(1)}%`, sub: "日度胜率", tone: k.winRate >= 0.5 ? "up" : "flat" },
    { key: "volatility", label: "年化波动", value: `${(k.volatility * 100).toFixed(2)}%`, sub: "年化标准差", tone: k.volatility <= 0.15 ? "up" : k.volatility <= 0.25 ? "flat" : "down" },
  ];
}

// 构建指标明细分组
function buildMetrics(points: NavPoint[], kpis: ApiStrategyDetail["kpis"]): MetricGroup[] {
  const stats = computeStats(points);
  return [
    {
      title: "收益", en: "RETURN",
      items: [
        { label: "累计收益率", value: `${(stats.total * 100).toFixed(2)}%`, tone: "up" as const },
        { label: "年化收益率", value: `${(stats.annual * 100).toFixed(2)}%`, tone: "up" as const },
        { label: "超额收益", value: `${((kpis.annualReturn - 0.03) * 100).toFixed(2)}%`, tone: "up" as const },
        { label: "Calmar", value: stats.calmar.toFixed(2), tone: "up" as const },
      ],
    },
    {
      title: "风险", en: "RISK",
      items: [
        { label: "最大回撤", value: `${(stats.maxDd * 100).toFixed(2)}%`, tone: "down" as const },
        { label: "年化波动", value: `${(kpis.volatility * 100).toFixed(2)}%`, tone: "flat" as const },
        { label: "VaR 95%", value: `${(stats.var95 * 100).toFixed(2)}%`, tone: "down" as const },
        { label: "最大持仓比", value: "—", tone: "flat" as const },
      ],
    },
    {
      title: "质量", en: "QUALITY",
      items: [
        { label: "夏普比率", value: kpis.sharpe.toFixed(3), tone: "up" as const },
        { label: "Sortino", value: stats.sortino.toFixed(3), tone: "up" as const },
        { label: "日胜率", value: `${(kpis.winRate * 100).toFixed(1)}%`, tone: "up" as const },
        { label: "盈亏比", value: "—", tone: "flat" as const },
      ],
    },
  ];
}

const SUB_COLORS = ["#22D3EE", "#A78BFA", "#F43F5E", "#34D399", "#FBBF24", "#60A5FA"];

/** 聚合当前选中策略/周期/基准下的全部面板数据 */
export function useDashboard() {
  const strategyId = useDashStore((s) => s.strategyId);
  const period = useDashStore((s) => s.period);
  const benchmarkKey = useDashStore((s) => s.benchmarkKey);

  const [detail, setDetail] = useState<ApiStrategyDetail | null>(null);

  useEffect(() => {
    let cancelled = false;
    getStrategyDetail(strategyId, period, benchmarkKey)
      .then((d) => { if (!cancelled) setDetail(d); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [strategyId, period, benchmarkKey]);

  return useMemo(() => {
    if (!detail) {
      return {
        def: { id: strategyId, name: "加载中…", tag: "", status: "running" as const, version: "" },
        bench: BENCHMARKS[0],
        period,
        points: [] as NavPoint[],
        stats: { total: 0, annual: 0, sharpe: 0, sortino: 0, calmar: 0, maxDd: 0, vol: 0, var95: 0, mar: 0 },
        kpis: [] as any[],
        metricGroups: [] as MetricGroup[],
        holdings: [] as any[],
        trades: [] as any[],
        subStrategies: [] as any[],
      };
    }

    const bench = BENCHMARKS.find((b) => b.key === benchmarkKey) ?? BENCHMARKS[0];
    const points = toPoints(detail.nav);

    // 子策略补充 color + contribution（API 只返回 id/name/weight）
    const subs = (detail.subStrategies || []).map((s, i) => ({
      ...s,
      color: SUB_COLORS[i % SUB_COLORS.length],
      contribution: 0,
    }));

    return {
      def: { id: detail.id, name: detail.name, tag: detail.tag, status: detail.status, version: detail.version },
      bench,
      period,
      points,
      stats: computeStats(points),
      kpis: buildKpis(detail),
      metricGroups: buildMetrics(points, detail.kpis),
      holdings: detail.holdings || [],
      trades: detail.trades || [],
      subStrategies: subs,
    };
  }, [detail, benchmarkKey, period, strategyId]);
}
