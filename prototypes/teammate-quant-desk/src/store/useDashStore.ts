import { create } from "zustand";
import { BENCHMARKS, STRATEGIES } from "@/data/mock";

interface DashState {
  strategyId: string;
  period: string;
  benchmarkKey: string;
  notice: string | null;
  setStrategy: (id: string) => void;
  setPeriod: (p: string) => void;
  setBenchmark: (k: string) => void;
  notify: (msg: string) => void;
}

let noticeTimer: ReturnType<typeof setTimeout> | undefined;

export const useDashStore = create<DashState>((set) => ({
  strategyId: STRATEGIES[0].id,
  period: "1Y",
  benchmarkKey: BENCHMARKS[0].key,
  notice: null,
  setStrategy: (strategyId) => set({ strategyId }),
  setPeriod: (period) => set({ period }),
  setBenchmark: (benchmarkKey) => set({ benchmarkKey }),
  notify: (msg) => {
    if (noticeTimer) clearTimeout(noticeTimer);
    noticeTimer = setTimeout(() => set({ notice: null }), 2200);
    set({ notice: msg });
  },
}));
