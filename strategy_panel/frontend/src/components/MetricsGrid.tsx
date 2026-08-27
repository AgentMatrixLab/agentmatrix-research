import Card from "./Card";
import { useDashboard } from "@/hooks/useDashboard";
import { cn } from "@/lib/utils";

const TONE: Record<string, string> = {
  up: "text-up",
  down: "text-down",
  flat: "text-fg",
};

export default function MetricsGrid() {
  const { metricGroups } = useDashboard();
  return (
    <Card title="指标明细" en="METRICS" delay={240} pad={false}>
      <div className="grid grid-cols-3 divide-x divide-line">
        {metricGroups.map((g) => (
          <div key={g.title}>
            <div className="flex items-baseline gap-2 px-5 pt-4">
              <h3 className="text-xs font-semibold text-fg">{g.title}</h3>
              <span className="text-[10px] font-medium uppercase tracking-[0.2em] text-fg-mute">
                {g.en}
              </span>
            </div>
            <ul className="px-5 py-3">
              {g.items.map((it) => (
                <li
                  key={it.label}
                  className="flex items-center justify-between border-b border-line/40 py-2 last:border-0"
                >
                  <span className="text-xs text-fg-soft">{it.label}</span>
                  <span className={cn("num text-[13px] font-semibold", TONE[it.tone ?? "flat"])}>
                    {it.value}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </Card>
  );
}
