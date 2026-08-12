import { useMemo } from "react";
import { BENCHMARKS, STRATEGIES, computeWindow, strategyDataMap } from "@/data/mock";
import { useDashStore } from "@/store/useDashStore";

/** 聚合当前选中策略/周期/基准下的全部面板数据 */
export function useDashboard() {
  const strategyId = useDashStore((s) => s.strategyId);
  const period = useDashStore((s) => s.period);
  const benchmarkKey = useDashStore((s) => s.benchmarkKey);

  return useMemo(() => {
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
  }, [strategyId, period, benchmarkKey]);
}
