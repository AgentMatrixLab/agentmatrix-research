import { cn } from "@/lib/utils";

export interface Stat {
  label: string;
  value: string;
  sub?: string;
  tone?: "up" | "down" | "flat" | "accent";
}

const TONE: Record<string, string> = {
  up: "text-up",
  down: "text-down",
  flat: "text-fg",
  accent: "text-accent",
};

/** 通用统计条：各页面顶部的迷你 KPI 行 */
export default function StatStrip({ stats, delay = 40 }: { stats: Stat[]; delay?: number }) {
  return (
    <div
      className="reveal card-hover grid rounded-xl border border-line bg-ink-800 shadow-card"
      style={{
        gridTemplateColumns: `repeat(${stats.length}, minmax(0, 1fr))`,
        animationDelay: `${delay}ms`,
      }}
    >
      {stats.map((s, i) => (
        <div key={s.label} className={cn("px-5 py-3.5", i !== 0 && "border-l border-line/60")}>
          <p className="text-[11px] font-medium text-fg-mute">{s.label}</p>
          <p className={cn("num mt-1 text-[22px] font-bold leading-none", TONE[s.tone ?? "flat"])}>
            {s.value}
          </p>
          {s.sub && <p className="num mt-1.5 text-[11px] text-fg-mute">{s.sub}</p>}
        </div>
      ))}
    </div>
  );
}
