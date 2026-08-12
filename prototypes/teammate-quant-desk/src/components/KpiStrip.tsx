import { TrendingDown, TrendingUp } from "lucide-react";
import { cn } from "@/lib/utils";
import { useDashboard } from "@/hooks/useDashboard";

const TONE: Record<string, string> = {
  up: "text-up",
  down: "text-down",
  accent: "text-fg",
};

export default function KpiStrip() {
  const { kpis } = useDashboard();
  return (
    <div
      className="reveal card-hover grid grid-cols-6 rounded-xl border border-line bg-ink-800 shadow-card"
      style={{ animationDelay: "60ms" }}
    >
      {kpis.map((k, i) => (
        <div
          key={k.key}
          className={cn(
            "relative px-5 py-4",
            i !== 0 && "border-l border-line/60"
          )}
        >
          <p className="flex items-center gap-1.5 text-[11px] font-medium text-fg-mute">
            {k.label}
            {k.tone === "up" && <TrendingUp size={12} className="text-up" />}
            {k.tone === "down" && <TrendingDown size={12} className="text-down" />}
          </p>
          <p
            className={cn(
              "num mt-1.5 font-bold leading-none tracking-tight",
              i === 0 ? "text-[30px]" : "text-[24px]",
              TONE[k.tone]
            )}
          >
            {k.value}
          </p>
          <p className="num mt-2 text-[11px] text-fg-mute">{k.sub}</p>
          {i === 0 && (
            <span className="absolute inset-x-5 bottom-0 h-[2px] rounded-full bg-gradient-to-r from-up/80 to-transparent" />
          )}
        </div>
      ))}
    </div>
  );
}
