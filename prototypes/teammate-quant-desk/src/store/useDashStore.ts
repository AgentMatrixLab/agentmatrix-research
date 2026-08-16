import { create } from "zustand";
import { BENCHMARKS, STRATEGIES } from "@/data/mock";
import type { CanonicalStrategyDetail, CanonicalStrategySummary } from "@/api/types";

interface DashState {
  strategyId: string;
  period: string;
  benchmarkKey: string;
  notice: string | null;
  source: "loading" | "live" | "demo";
  strategies: CanonicalStrategySummary[];
  details: Record<string, CanonicalStrategyDetail>;
  setStrategy: (id: string) => void;
  setPeriod: (p: string) => void;
  setBenchmark: (k: string) => void;
  notify: (msg: string) => void;
  loadLive: () => Promise<void>;
}

let noticeTimer: ReturnType<typeof setTimeout> | undefined;

export const useDashStore = create<DashState>((set) => ({
  strategyId: STRATEGIES[0].id,
  period: "1Y",
  benchmarkKey: BENCHMARKS[0].key,
  notice: null,
  source: "loading",
  strategies: [],
  details: {},
  setStrategy: (strategyId) => set({ strategyId }),
  setPeriod: (period) => set({ period }),
  setBenchmark: (benchmarkKey) => set({ benchmarkKey }),
  notify: (msg) => {
    if (noticeTimer) clearTimeout(noticeTimer);
    noticeTimer = setTimeout(() => set({ notice: null }), 2200);
    set({ notice: msg });
  },
  loadLive: async () => {
    try {
      const { listCanonicalStrategies, getCanonicalStrategy } = await import("@/api");
      const strategies = await listCanonicalStrategies();
      if (!strategies.length) throw new Error("empty strategy registry");
      const loaded = await Promise.all(strategies.map(s => getCanonicalStrategy(s.id)));
      const details = Object.fromEntries(loaded.map(d => [d.id, d]));
      set(state => ({source:"live", strategies, details, strategyId: details[state.strategyId] ? state.strategyId : strategies[0].id}));
    } catch {
      set({source:"demo"});
    }
  },
}));
