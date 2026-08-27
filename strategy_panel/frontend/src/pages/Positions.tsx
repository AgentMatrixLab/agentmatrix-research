import { useEffect, useMemo, useState } from "react";
import ReactECharts from "echarts-for-react";
import type { EChartsOption } from "echarts";
import Card from "@/components/Card";
import StatStrip from "@/components/StatStrip";
import HoldingsTable from "@/components/HoldingsTable";
import { getPositions, type PositionOverview } from "@/api";
import { useDashStore } from "@/store/useDashStore";
import { STRATEGIES } from "@/data/mock";
import { cn } from "@/lib/utils";

const DONUT_COLORS = ["#22D3EE", "#67E8F9", "#0E7490", "#94A3B8", "#475569", "#F43F5E", "#10B981", "#334155"];

export default function Positions() {
  const strategyId = useDashStore((s) => s.strategyId);
  const [data, setData] = useState<PositionOverview | null>(null);

  useEffect(() => {
    setData(null);
    getPositions(strategyId).then(setData);
  }, [strategyId]);

  const def = STRATEGIES.find((s) => s.id === strategyId);

  const donutOption = useMemo<EChartsOption | null>(() => {
    if (!data) return null;
    return {
      animationDuration: 700,
      tooltip: {
        backgroundColor: "rgba(13,18,25,0.96)",
        borderColor: "rgba(148,163,184,0.16)",
        textStyle: { color: "#E2E8F0", fontSize: 11, fontFamily: "JetBrains Mono" },
        formatter: (p) => {
          const item = p as { name: string; value: number };
          return `${item.name}　${item.value.toFixed(1)}%`;
        },
      },
      series: [
        {
          type: "pie",
          radius: ["58%", "82%"],
          center: ["50%", "50%"],
          label: { show: false },
          emphasis: { scaleSize: 4 },
          itemStyle: { borderColor: "#11161F", borderWidth: 3, borderRadius: 4 },
          data: data.rows.map((r, i) => ({
            name: r.name,
            value: +(r.weight * 100).toFixed(1),
            itemStyle: { color: DONUT_COLORS[i % DONUT_COLORS.length] },
          })),
        },
      ],
    };
  }, [data]);

  if (!data) {
    return (
      <main className="mx-auto max-w-[1600px] px-6 py-5">
        <div className="animate-pulse space-y-4">
          <div className="h-20 rounded-xl bg-ink-700/50" />
          <div className="h-64 rounded-xl bg-ink-700/50" />
        </div>
      </main>
    );
  }

  const maxInd = Math.max(...data.industries.map((i) => i.weight), 0.0001);

  return (
    <main className="mx-auto max-w-[1600px] space-y-4 px-6 py-5">
      <p className="text-[11px] text-fg-mute">
        当前策略：<span className="font-medium text-fg-soft">{def?.name}</span>（在左侧「我的策略」切换）
      </p>

      {/* 汇总条 */}
      <StatStrip
        stats={[
          { label: "持仓只数", value: `${data.count}` },
          { label: "总仓位", value: `${(data.totalWeight * 100).toFixed(1)}%`, tone: "accent" },
          { label: "前五大集中度", value: `${(data.top5Weight * 100).toFixed(1)}%` },
          { label: "HHI 集中度", value: data.hhi.toFixed(3), sub: "越低越分散" },
        ]}
      />

      {/* 分布图组 */}
      <div className="grid grid-cols-12 gap-4">
        {/* 行业分布 */}
        <Card title="行业分布" en="INDUSTRY" delay={100} pad={false} className="col-span-4">
          <div className="space-y-3 p-5">
            {data.industries.map((ind) => (
              <div key={ind.name}>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-fg-soft">{ind.name}</span>
                  <span className="num text-fg">{(ind.weight * 100).toFixed(1)}%</span>
                </div>
                <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-ink-600">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-accent/50 to-accent"
                    style={{ width: `${(ind.weight / maxInd) * 100}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </Card>

        {/* 个股市值占比 */}
        <Card title="个股市值占比" en="WEIGHTS" delay={140} pad={false} className="col-span-4">
          <div className="relative mx-auto h-[210px] w-[210px] pt-3">
            {donutOption && (
              <ReactECharts option={donutOption} notMerge style={{ height: "100%", width: "100%" }} />
            )}
            <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
              <span className="num text-xl font-bold text-fg">{data.count}</span>
              <span className="mt-0.5 text-[10px] tracking-[0.2em] text-fg-mute">只持仓</span>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 px-5 pb-4">
            {data.rows.slice(0, 6).map((r, i) => (
              <div key={r.code} className="flex items-center gap-1.5 text-[11px]">
                <span
                  className="h-2 w-2 shrink-0 rounded-sm"
                  style={{ background: DONUT_COLORS[i % DONUT_COLORS.length] }}
                />
                <span className="truncate text-fg-soft">{r.name}</span>
                <span className="num ml-auto text-fg-mute">{(r.weight * 100).toFixed(1)}%</span>
              </div>
            ))}
          </div>
        </Card>

        {/* 市值风格 */}
        <Card title="市值风格" en="CAP STYLE" delay={180} pad={false} className="col-span-4">
          <div className="space-y-4 p-5">
            {data.marketCap.map((c) => (
              <div key={c.label}>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-fg-soft">{c.label}</span>
                  <span className="num text-fg">{(c.weight * 100).toFixed(1)}%</span>
                </div>
                <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-ink-600">
                  <div
                    className={cn(
                      "h-full rounded-full",
                      c.label === "大盘" && "bg-accent",
                      c.label === "中盘" && "bg-cyan-700",
                      c.label === "小盘" && "bg-slate-500"
                    )}
                    style={{ width: `${c.weight * 100}%` }}
                  />
                </div>
              </div>
            ))}
            <p className="border-t border-line/60 pt-3 text-[11px] leading-relaxed text-fg-mute">
              风格暴露基于最新持仓市值加权；大盘占比越高组合波动通常越低。
            </p>
          </div>
        </Card>
      </div>

      {/* 持仓明细 */}
      <Card title="持仓明细" en="POSITIONS" delay={220} pad={false}>
        <div className="scroll-slim max-h-[420px] overflow-auto">
          <HoldingsTable holdings={data.rows} showIndustry />
        </div>
      </Card>
    </main>
  );
}
