import { useMemo } from "react";
import ReactECharts from "echarts-for-react";
import type { EChartsOption } from "echarts";
import { TrendingDown, TrendingUp, Layers } from "lucide-react";
import { cn } from "@/lib/utils";
import { useOverview } from "@/hooks/useOverview";

const FOLIO_COLORS = ["#6366f1", "#f43f5e", "#3b82f6", "#f59e0b", "#22c55e", "#8b5cf6"];

function pct(v: number) { return `${(v * 100).toFixed(2)}%`; }
function pctSigned(v: number) { return `${v >= 0 ? "+" : ""}${(v * 100).toFixed(2)}%`; }

function FolioKpiCard({ label, value, tone, sub }: {
  label: string; value: string; tone: "up" | "down" | "accent"; sub: string;
}) {
  const TONE = { up: "text-up", down: "text-down", accent: "text-fg" } as const;
  return (
    <div className="relative px-5 py-4 border-r border-line/60 last:border-r-0">
      <p className="flex items-center gap-1.5 text-[11px] font-medium text-fg-mute">
        {label}
        {tone === "up" && <TrendingUp size={12} className="text-up" />}
        {tone === "down" && <TrendingDown size={12} className="text-down" />}
      </p>
      <p className={cn("num mt-1.5 text-[24px] font-bold leading-none tracking-tight", TONE[tone])}>
        {value}
      </p>
      <p className="num mt-2 text-[11px] text-fg-mute">{sub}</p>
    </div>
  );
}

export default function FolioSection() {
  const { folio, loading } = useOverview();

  const navOption = useMemo<EChartsOption>(() => {
    if (!folio?.navDates) return {};
    return {
      animationDuration: 800,
      tooltip: {
        backgroundColor: "rgba(13,18,25,0.96)",
        borderColor: "rgba(148,163,184,0.16)",
        textStyle: { color: "#E2E8F0", fontSize: 11, fontFamily: "JetBrains Mono" },
        trigger: "axis",
      },
      grid: { left: 48, right: 16, top: 12, bottom: 28 },
      xAxis: {
        type: "category",
        data: folio.navDates,
        axisLine: { lineStyle: { color: "#1e293b" } },
        axisLabel: { color: "#64748b", fontSize: 10, formatter: (v: string) => v.slice(0, 10) },
        axisTick: { show: false },
      },
      yAxis: {
        type: "value",
        splitLine: { lineStyle: { color: "#1e293b", type: "dashed" } },
        axisLabel: { color: "#64748b", fontSize: 10, formatter: (v: number) => v < 2 ? v.toFixed(2) : v.toFixed(1) },
      },
      series: [{
        name: "组合净值",
        type: "line",
        data: folio.navValues,
        smooth: true,
        symbol: "none",
        lineStyle: { color: "#6366f1", width: 2 },
        itemStyle: { color: "#6366f1" },
        areaStyle: { color: { type: "linear", x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [{ offset: 0, color: "rgba(99,102,241,0.15)" }, { offset: 1, color: "rgba(99,102,241,0)" }] } },
      }],
    };
  }, [folio]);

  const pieOption = useMemo<EChartsOption>(() => {
    if (!folio?.weights) return {};
    const entries = Object.entries(folio.weights);
    return {
      animationDuration: 600,
      tooltip: {
        backgroundColor: "rgba(13,18,25,0.96)",
        borderColor: "rgba(148,163,184,0.16)",
        textStyle: { color: "#E2E8F0", fontSize: 11, fontFamily: "JetBrains Mono" },
        formatter: (p: any) => `${p.name}　权重 ${p.value}%`,
      },
      series: [{
        type: "pie",
        radius: ["62%", "82%"],
        center: ["50%", "50%"],
        avoidLabelOverlap: false,
        label: { show: false },
        emphasis: { scaleSize: 4 },
        itemStyle: { borderColor: "#11161F", borderWidth: 3, borderRadius: 4 },
        data: entries.map(([sid, w], i) => ({
          name: sid,
          value: Number((w * 100).toFixed(1)),
          itemStyle: { color: FOLIO_COLORS[i % FOLIO_COLORS.length] },
        })),
      }],
    };
  }, [folio]);

  if (loading) {
    return (
      <section className="reveal rounded-xl border border-line bg-ink-800 shadow-card px-5 py-10 text-center">
        <p className="text-sm text-fg-mute">加载策略组合中…</p>
      </section>
    );
  }

  if (!folio) {
    return (
      <section className="reveal rounded-xl border border-line bg-ink-800 shadow-card px-5 py-8 text-center">
        <Layers size={32} className="mx-auto mb-3 text-fg-mute" />
        <p className="text-sm text-fg-soft">当前策略不足，无法构建投资组合</p>
        <p className="mt-1 text-[11px] text-fg-mute">至少需要 2 个策略才能自动组合</p>
      </section>
    );
  }

  const entries = Object.entries(folio.weights);
  const annRet = folio.annualReturn;
  const totRet = folio.totalReturn;
  const mdd = folio.maxDrawdown;
  const vol = folio.volatility;

  return (
    <section className="reveal rounded-xl border border-line bg-ink-800 shadow-card" style={{ animationDelay: "40ms" }}>
      {/* 标题 */}
      <header className="flex items-center justify-between gap-3 border-b border-line px-5 py-3.5">
        <div className="flex items-baseline gap-2.5">
          <span className="h-3.5 w-[3px] translate-y-[1px] rounded-full bg-accent" />
          <h2 className="text-sm font-semibold tracking-wide text-fg">
            策略组合 · {folio.name || "TOP 5 逆波动率加权"}
          </h2>
          <span className="text-[10px] font-medium uppercase tracking-[0.2em] text-fg-mute">PORTFOLIO</span>
        </div>
        <span className="text-[11px] text-fg-mute">
          Top 5 按年化收益 · 逆波动率加权 · 每日再平衡
        </span>
      </header>

      {/* KPI 条 */}
      <div className="grid grid-cols-5 border-b border-line/60">
        <FolioKpiCard label="年化收益" value={pct(annRet)} tone={annRet >= 0 ? "up" : "down"} sub="年化复利" />
        <FolioKpiCard label="累计收益" value={pct(totRet)} tone={totRet >= 0 ? "up" : "down"} sub="策略区间" />
        <FolioKpiCard label="夏普比率" value={folio.sharpe.toFixed(2)} tone={folio.sharpe >= 1 ? "up" : folio.sharpe >= 0.5 ? "accent" : "down"} sub="风险调整收益" />
        <FolioKpiCard label="最大回撤" value={pct(mdd)} tone={mdd <= 0.15 ? "up" : mdd <= 0.25 ? "accent" : "down"} sub="峰值到谷底" />
        <FolioKpiCard label="年化波动" value={pct(vol)} tone={vol <= 0.2 ? "up" : vol <= 0.3 ? "accent" : "down"} sub="年化标准差" />
      </div>

      {/* 净值图 + 权重饼图 */}
      <div className="grid grid-cols-12 gap-0">
        <div className="col-span-8 h-[300px] border-r border-line/60">
          {folio.navDates?.length > 1 ? (
            <ReactECharts option={navOption} notMerge style={{ height: "100%", width: "100%" }} />
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-fg-mute">暂无净值数据</div>
          )}
        </div>

        <div className="col-span-4 flex flex-col">
          {/* 饼图 */}
          <div className="relative flex-1">
            <ReactECharts option={pieOption} notMerge style={{ height: "100%", width: "100%" }} />
            <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
              <span className="num text-2xl font-bold text-fg">{entries.length}</span>
              <span className="mt-0.5 text-[10px] tracking-[0.2em] text-fg-mute">只策略</span>
            </div>
          </div>

          {/* 权重图例 */}
          <div className="space-y-2 px-5 pb-4">
            {entries.map(([sid, w], i) => (
              <div key={sid} className="group">
                <div className="flex items-center gap-2 text-xs">
                  <span className="h-2 w-2 rounded-sm" style={{ background: FOLIO_COLORS[i % FOLIO_COLORS.length] }} />
                  <span className="truncate text-fg-soft group-hover:text-fg">{sid}</span>
                  <span className="num ml-auto w-12 text-right text-[11px] font-semibold text-fg-mute">
                    {(w * 100).toFixed(1)}%
                  </span>
                </div>
                <div className="mt-1 h-1 overflow-hidden rounded-full bg-ink-600">
                  <div
                    className="h-full rounded-full transition-all duration-500"
                    style={{ width: `${w * 100}%`, background: FOLIO_COLORS[i % FOLIO_COLORS.length] }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
