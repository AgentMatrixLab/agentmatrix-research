import { useMemo } from "react";
import { BENCHMARKS, STRATEGIES, computeWindow, strategyDataMap } from "@/data/mock";
import { useDashStore } from "@/store/useDashStore";
import { liveDashboard, liveDefinition } from "@/data/live";

/** 聚合当前选中策略/周期/基准下的全部面板数据 */
export function useDashboard() {
  const strategyId = useDashStore((s) => s.strategyId);
  const period = useDashStore((s) => s.period);
  const benchmarkKey = useDashStore((s) => s.benchmarkKey);
  const liveStrategies = useDashStore((s) => s.strategies);
  const details = useDashStore((s) => s.details);
  const source = useDashStore((s) => s.source);

  return useMemo(() => {
    const summary = liveStrategies.find(s => s.id === strategyId);
    if (source === "live" && summary && details[strategyId]) {
      const full = liveDashboard(details[strategyId]);
      const def = liveDefinition(summary);
      const bench = {key:"canonical",name:details[strategyId].benchmark || "策略基准"};
      return {def,bench,period,...full};
    }
    const def = STRATEGIES.find((s) => s.id === strategyId) ?? STRATEGIES[0];
    const bench = BENCHMARKS.find((b) => b.key === benchmarkKey) ?? BENCHMARKS[0];
    const data = strategyDataMap[def.id];
    const win = computeWindow(def.id, bench.key, period);
    return {
      def,
      bench,
      period,
      points: win.points,
      stats: win.stats,
      kpis: win.kpis,
      metricGroups: win.metricGroups,
      holdings: data.holdings,
      trades: data.trades,
      subStrategies: data.subStrategies,
    };
  }, [strategyId, period, benchmarkKey, liveStrategies, details, source]);
}
