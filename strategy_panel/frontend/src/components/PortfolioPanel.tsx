import { useMemo } from "react";
import ReactECharts from "echarts-for-react";
import type { EChartsOption } from "echarts";
import Card from "./Card";
import { useDashboard } from "@/hooks/useDashboard";
import { cn } from "@/lib/utils";

export default function PortfolioPanel({ className }: { className?: string }) {
  const { subStrategies } = useDashboard();
  const option = useMemo<EChartsOption>(
    () => ({
      animationDuration: 900,
      tooltip: {
        backgroundColor: "rgba(13,18,25,0.96)",
        borderColor: "rgba(148,163,184,0.16)",
        textStyle: { color: "#E2E8F0", fontSize: 11, fontFamily: "JetBrains Mono" },
        formatter: (p) => {
          const item = p as { name: string; value: number };
          return `${item.name}　权重 ${item.value}%`;
        },
      },
      series: [
        {
          type: "pie",
          radius: ["64%", "84%"],
          center: ["50%", "50%"],
          avoidLabelOverlap: true,
          label: { show: false },
          emphasis: { scaleSize: 4 },
          itemStyle: { borderColor: "#11161F", borderWidth: 3, borderRadius: 4 },
          data: subStrategies.map((s) => ({
            name: s.name,
            value: +(s.weight * 100).toFixed(0),
            itemStyle: { color: s.color },
          })),
        },
      ],
    }),
    [subStrategies]
  );

  return (
    <Card title="组合策略" en="PORTFOLIO" delay={180} pad={false} className={cn("flex flex-col", className)}>
      {/* 环形图 */}
      <div className="relative mx-auto mt-4 h-[190px] w-[190px]">
        <ReactECharts option={option} notMerge style={{ height: "100%", width: "100%" }} />
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
          <span className="num text-2xl font-bold text-fg">{subStrategies.length}</span>
          <span className="mt-0.5 text-[10px] tracking-[0.2em] text-fg-mute">子策略</span>
        </div>
      </div>

      {/* 权重列表 */}
      <div className="mt-2 flex-1 space-y-3 px-5 pb-5">
        {subStrategies.map((s) => {
          const up = s.contribution >= 0;
          return (
            <div key={s.name} className="group">
              <div className="flex items-center gap-2 text-xs">
                <span
                  className="h-2 w-2 rounded-sm"
                  style={{ background: s.color }}
                />
                <span className="text-fg-soft group-hover:text-fg">{s.name}</span>
                <span className={cn("num ml-auto text-[11px] font-semibold", up ? "text-up" : "text-down")}>
                  贡献 {up ? "+" : ""}
                  {(s.contribution * 100).toFixed(1)}%
                </span>
                <span className="num w-10 text-right text-[11px] text-fg-mute">
                  {(s.weight * 100).toFixed(0)}%
                </span>
              </div>
              <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-ink-600">
                <div
                  className="h-full rounded-full transition-all duration-500"
                  style={{ width: `${s.weight * 100}%`, background: s.color }}
                />
              </div>
            </div>
          );
        })}
      </div>

      <div className="border-t border-line px-5 py-3 text-[11px] text-fg-mute">
        月度再平衡 · 目标波动率 15%
      </div>
    </Card>
  );
}
