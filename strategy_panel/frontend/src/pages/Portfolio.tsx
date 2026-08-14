import { useEffect, useMemo, useState } from "react";
import ReactECharts from "echarts-for-react";
import * as echarts from "echarts";
import type { EChartsOption } from "echarts";
import {
  AlertTriangle,
  CheckCircle2,
  Equal,
  Layers,
  Play,
  Plus,
  Save,
  Sparkles,
  X,
} from "lucide-react";
import Card from "@/components/Card";
import StatStrip from "@/components/StatStrip";
import { cn } from "@/lib/utils";
import {
  PRESET_PORTFOLIOS,
  listStrategies,
  runPortfolioBacktest,
  type ApiStrategySummary,
  type PortfolioBacktestResult,
} from "@/api";
import { dates } from "@/data/mock";
import { useDashStore } from "@/store/useDashStore";

const STRATEGY_COLORS = ["#22D3EE", "#67E8F9", "#0E7490", "#94A3B8", "#F43F5E"];

/* ---------- 组合净值小图 ---------- */
function buildResultOption(result: PortfolioBacktestResult): EChartsOption {
  const benchBase = result.nav[0]?.benchmark ?? 1;
  return {
    animationDuration: 700,
    grid: { left: 52, right: 18, top: 24, bottom: 28 },
    tooltip: {
      trigger: "axis",
      backgroundColor: "rgba(13,18,25,0.96)",
      borderColor: "rgba(148,163,184,0.16)",
      textStyle: { color: "#E2E8F0", fontSize: 11, fontFamily: "JetBrains Mono" },
    },
    xAxis: {
      type: "category",
      data: result.nav.map((p) => p.date),
      boundaryGap: false,
      axisLine: { lineStyle: { color: "rgba(148,163,184,0.12)" } },
      axisTick: { show: false },
      axisLabel: { color: "#566173", fontSize: 10, fontFamily: "JetBrains Mono", hideOverlap: true },
    },
    yAxis: {
      type: "value",
      scale: true,
      splitLine: { lineStyle: { color: "rgba(148,163,184,0.07)" } },
      axisLabel: {
        color: "#566173",
        fontSize: 10,
        fontFamily: "JetBrains Mono",
        formatter: (v: number) => v.toFixed(2),
      },
    },
    series: [
      {
        name: "组合净值",
        type: "line",
        data: result.nav.map((p) => +p.nav.toFixed(4)),
        showSymbol: false,
        smooth: 0.12,
        lineStyle: { width: 2, color: "#22D3EE" },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: "rgba(34,211,238,0.22)" },
            { offset: 1, color: "rgba(34,211,238,0)" },
          ]),
        },
      },
      {
        name: "沪深300",
        type: "line",
        data: result.nav.map((p) => +(p.benchmark / benchBase).toFixed(4)),
        showSymbol: false,
        lineStyle: { width: 1, type: "dashed", color: "#64748B" },
      },
    ],
  };
}

/* ---------- 策略池条目 ---------- */
function PoolItem({
  s,
  checked,
  onToggle,
}: {
  s: ApiStrategySummary;
  checked: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      onClick={onToggle}
      className={cn(
        "flex w-full items-center gap-3 rounded-lg border px-3 py-2.5 text-left transition-colors",
        checked
          ? "border-accent/40 bg-accent/[0.07]"
          : "border-line/60 hover:border-line hover:bg-ink-700"
      )}
    >
      <span
        className={cn(
          "flex h-4 w-4 shrink-0 items-center justify-center rounded border transition-colors",
          checked ? "border-accent bg-accent text-ink-950" : "border-line"
        )}
      >
        {checked && <Plus size={12} strokeWidth={3} />}
      </span>
      <div className="min-w-0 flex-1">
        <p className={cn("truncate text-xs font-medium", checked ? "text-fg" : "text-fg-soft")}>
          {s.name}
        </p>
        <p className="mt-0.5 text-[10px] text-fg-mute">{s.tag}</p>
      </div>
      <div className="num text-right text-[11px]">
        <p className={s.annualReturn >= 0 ? "text-up" : "text-down"}>
          {s.annualReturn >= 0 ? "+" : ""}
          {(s.annualReturn * 100).toFixed(1)}%
        </p>
        <p className="text-fg-mute">夏普 {s.sharpe.toFixed(2)}</p>
      </div>
    </button>
  );
}

export default function Portfolio() {
  const notify = useDashStore((s) => s.notify);
  const [strategies, setStrategies] = useState<ApiStrategySummary[]>([]);
  const [weights, setWeights] = useState<Record<string, number>>({});
  const [comboName, setComboName] = useState("我的组合");
  const [rebalance, setRebalance] = useState<"weekly" | "monthly" | "quarterly">("monthly");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<PortfolioBacktestResult | null>(null);

  useEffect(() => {
    listStrategies().then(setStrategies);
  }, []);

  const selectedIds = Object.keys(weights);
  const totalWeight = selectedIds.reduce((a, id) => a + weights[id], 0);
  const canRun = selectedIds.length >= 2 && totalWeight === 100 && !running;

  const toggle = (id: string) => {
    setResult(null);
    setWeights((prev) => {
      const next = { ...prev };
      if (id in next) delete next[id];
      else next[id] = 0;
      return next;
    });
  };

  const distributeEvenly = () => {
    const n = selectedIds.length;
    if (n === 0) return;
    const base = Math.floor(100 / n);
    const next: Record<string, number> = {};
    selectedIds.forEach((id, i) => {
      next[id] = i === 0 ? 100 - base * (n - 1) : base;
    });
    setWeights(next);
  };

  const loadPreset = (items: { strategyId: string; weight: number }[], name: string) => {
    const next: Record<string, number> = {};
    items.forEach((it) => {
      next[it.strategyId] = Math.round(it.weight * 100);
    });
    setWeights(next);
    setComboName(name);
    setResult(null);
    notify(`已载入预设组合「${name}」`);
  };

  const run = () => {
    setRunning(true);
    setResult(null);
    runPortfolioBacktest({
      items: selectedIds.map((id) => ({ strategyId: id, weight: weights[id] / 100 })),
      rebalance,
      start: dates[0],
      end: dates[dates.length - 1],
    })
      .then((res) => setResult(res))
      .finally(() => setRunning(false));
  };

  const chartOption = useMemo(
    () => (result ? buildResultOption(result) : null),
    [result]
  );

  return (
    <main className="mx-auto max-w-[1600px] space-y-4 px-6 py-5">
      <div className="grid grid-cols-12 gap-4">
        {/* 左：策略池 + 预设组合 */}
        <div className="col-span-4 space-y-4">
          <Card title="策略池" en="STRATEGY POOL" delay={60} pad={false}>
            <div className="space-y-2 p-4">
              {strategies.map((s) => (
                <PoolItem key={s.id} s={s} checked={s.id in weights} onToggle={() => toggle(s.id)} />
              ))}
              <p className="px-1 pt-1 text-[11px] text-fg-mute">
                勾选至少 2 个策略加入组合 · 已选 <span className="num text-accent">{selectedIds.length}</span> 个
              </p>
            </div>
          </Card>

          <Card title="预设组合" en="PRESETS" delay={120} pad={false}>
            <div className="space-y-2 p-4">
              {PRESET_PORTFOLIOS.map((p) => (
                <button
                  key={p.name}
                  onClick={() => loadPreset(p.items, p.name)}
                  className="group w-full rounded-lg border border-line/60 px-3.5 py-3 text-left transition-colors hover:border-accent/30 hover:bg-ink-700"
                >
                  <div className="flex items-center gap-2">
                    <Sparkles size={13} className="text-accent" />
                    <span className="text-xs font-semibold text-fg">{p.name}</span>
                    <span className="num ml-auto text-[10px] text-fg-mute">
                      {p.items.length} 个策略
                    </span>
                  </div>
                  <p className="mt-1 text-[11px] text-fg-mute">{p.desc}</p>
                </button>
              ))}
            </div>
          </Card>
        </div>

        {/* 右：组合配置 + 回测结果 */}
        <div className="col-span-8 space-y-4">
          <Card
            title="组合配置"
            en="ALLOCATION"
            delay={100}
            pad={false}
            actions={
              <button
                onClick={distributeEvenly}
                disabled={selectedIds.length === 0}
                className="flex items-center gap-1.5 rounded-md border border-line px-2.5 py-1 text-[11px] text-fg-soft transition-colors hover:border-accent/30 hover:text-fg disabled:opacity-40"
              >
                <Equal size={12} />
                平均分配
              </button>
            }
          >
            <div className="space-y-4 p-5">
              {/* 组合名 + 再平衡 */}
              <div className="grid grid-cols-2 gap-4">
                <label className="block">
                  <span className="mb-1.5 block text-[11px] text-fg-mute">组合名称</span>
                  <input
                    value={comboName}
                    onChange={(e) => setComboName(e.target.value)}
                    className="w-full rounded-lg border border-line bg-ink-900 px-3 py-2 text-xs text-fg outline-none transition-colors focus:border-accent/50"
                  />
                </label>
                <label className="block">
                  <span className="mb-1.5 block text-[11px] text-fg-mute">再平衡周期</span>
                  <select
                    value={rebalance}
                    onChange={(e) => setRebalance(e.target.value as typeof rebalance)}
                    className="w-full rounded-lg border border-line bg-ink-900 px-3 py-2 text-xs text-fg outline-none transition-colors focus:border-accent/50"
                  >
                    <option value="weekly">每周</option>
                    <option value="monthly">每月</option>
                    <option value="quarterly">每季度</option>
                  </select>
                </label>
              </div>

              {/* 权重滑杆 */}
              {selectedIds.length === 0 ? (
                <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed border-line py-8 text-fg-mute">
                  <Layers size={22} className="opacity-60" />
                  <p className="text-xs">从左侧策略池勾选策略，或载入预设组合</p>
                </div>
              ) : (
                <div className="space-y-3">
                  {selectedIds.map((id, i) => {
                    const s = strategies.find((x) => x.id === id);
                    const color = STRATEGY_COLORS[i % STRATEGY_COLORS.length];
                    return (
                      <div key={id} className="flex items-center gap-3">
                        <span className="h-2.5 w-2.5 shrink-0 rounded-sm" style={{ background: color }} />
                        <span className="w-28 truncate text-xs text-fg-soft">{s?.name ?? id}</span>
                        <input
                          type="range"
                          min={0}
                          max={100}
                          value={weights[id]}
                          onChange={(e) => {
                            setResult(null);
                            setWeights((prev) => ({ ...prev, [id]: Number(e.target.value) }));
                          }}
                          className="h-1 flex-1 cursor-pointer"
                        />
                        <span className="num w-14 text-right text-xs font-semibold text-fg">
                          {weights[id]}%
                        </span>
                        <button
                          onClick={() => toggle(id)}
                          className="rounded p-1 text-fg-mute transition-colors hover:text-up"
                        >
                          <X size={13} />
                        </button>
                      </div>
                    );
                  })}

                  {/* 合计校验 */}
                  <div className="flex items-center gap-2 border-t border-line/60 pt-3 text-[11px]">
                    {totalWeight === 100 ? (
                      <span className="flex items-center gap-1.5 text-down">
                        <CheckCircle2 size={13} />
                        权重合计 100%
                      </span>
                    ) : (
                      <span className="flex items-center gap-1.5 text-up">
                        <AlertTriangle size={13} />
                        权重合计 <span className="num">{totalWeight}%</span>，需等于 100%
                      </span>
                    )}
                    <div className="ml-auto flex gap-2">
                      <button
                        onClick={() => notify("演示环境 · 组合保存稍后接入后端")}
                        className="flex items-center gap-1.5 rounded-lg border border-line px-3.5 py-2 text-xs text-fg-soft transition-colors hover:border-accent/30 hover:text-fg"
                      >
                        <Save size={13} />
                        保存组合
                      </button>
                      <button
                        onClick={run}
                        disabled={!canRun}
                        className={cn(
                          "flex items-center gap-1.5 rounded-lg px-4 py-2 text-xs font-semibold transition-all",
                          canRun
                            ? "bg-accent text-ink-950 shadow-glow hover:brightness-110"
                            : "cursor-not-allowed bg-ink-600 text-fg-mute"
                        )}
                      >
                        <Play size={13} />
                        {running ? "回测中…" : "运行回测"}
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </Card>

          {/* 回测结果 */}
          {running && (
            <Card title="组合回测结果" en="RESULT" delay={0} pad={false}>
              <div className="animate-pulse space-y-3 p-5">
                <div className="h-16 rounded-lg bg-ink-700/60" />
                <div className="h-[280px] rounded-lg bg-ink-700/60" />
              </div>
            </Card>
          )}

          {!running && result && (
            <>
              <StatStrip
                stats={[
                  { label: "组合累计收益", value: `${result.kpis.totalReturn >= 0 ? "+" : ""}${(result.kpis.totalReturn * 100).toFixed(2)}%`, tone: result.kpis.totalReturn >= 0 ? "up" : "down" },
                  { label: "年化收益", value: `${result.kpis.annualReturn >= 0 ? "+" : ""}${(result.kpis.annualReturn * 100).toFixed(2)}%`, tone: result.kpis.annualReturn >= 0 ? "up" : "down" },
                  { label: "夏普比率", value: result.kpis.sharpe.toFixed(2) },
                  { label: "最大回撤", value: `${(result.kpis.maxDrawdown * 100).toFixed(2)}%`, tone: "down" },
                  { label: "日胜率", value: `${(result.kpis.winRate * 100).toFixed(1)}%` },
                  { label: "年化波动", value: `${(result.kpis.volatility * 100).toFixed(1)}%` },
                ]}
              />
              <Card
                title={`「${comboName}」组合净值`}
                en="PORTFOLIO NAV"
                delay={80}
                pad={false}
              >
                <div className="h-[300px] p-2">
                  {chartOption && (
                    <ReactECharts option={chartOption} notMerge style={{ height: "100%", width: "100%" }} />
                  )}
                </div>
              </Card>
            </>
          )}

          {!running && !result && (
            <Card title="组合回测结果" en="RESULT" delay={140} pad={false}>
              <div className="flex flex-col items-center gap-2.5 py-14 text-fg-mute">
                <Play size={26} className="opacity-50" />
                <p className="text-xs">配置权重后点击「运行回测」，此处将展示组合净值与指标</p>
              </div>
            </Card>
          )}
        </div>
      </div>
    </main>
  );
}
