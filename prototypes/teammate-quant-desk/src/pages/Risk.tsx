import { useEffect, useState, Fragment } from "react";
import { AlertTriangle, ShieldCheck } from "lucide-react";
import Card from "@/components/Card";
import StatStrip from "@/components/StatStrip";
import { cn } from "@/lib/utils";
import { getRiskOverview, type RiskOverview } from "@/api";
import { useDashStore } from "@/store/useDashStore";
import { STRATEGIES } from "@/data/mock";

const TH = "px-4 py-2.5 text-left text-[11px] font-medium text-fg-mute whitespace-nowrap";

/** 热力图着色：红涨绿跌，深浅按幅度 */
function heatColor(ret: number): string {
  const t = Math.min(Math.abs(ret) / 0.08, 1);
  return ret >= 0
    ? `rgba(244,63,94,${0.10 + 0.55 * t})`
    : `rgba(16,185,129,${0.10 + 0.55 * t})`;
}

export default function Risk() {
  const strategyId = useDashStore((s) => s.strategyId);
  const [data, setData] = useState<RiskOverview | null>(null);
  const [enabled, setEnabled] = useState<Record<string, boolean>>({});

  useEffect(() => {
    setData(null);
    getRiskOverview(strategyId).then((res) => {
      setData(res);
      const init: Record<string, boolean> = {};
      res.alerts.forEach((a) => {
        init[a.id] = a.enabled;
      });
      setEnabled(init);
    });
  }, [strategyId]);

  const def = STRATEGIES.find((s) => s.id === strategyId);

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

  const enabledCount = data.alerts.filter((a) => enabled[a.id]).length;
  const triggeredCount = data.alerts.filter((a) => a.triggered && enabled[a.id]).length;
  // 月度热力：按年份分组
  const years: Record<string, { month: string; ret: number }[]> = {};
  data.monthlyReturns.forEach((m) => {
    const y = m.month.slice(0, 4);
    (years[y] ??= []).push(m);
  });

  return (
    <main className="mx-auto max-w-[1600px] space-y-4 px-6 py-5">
      <p className="text-[11px] text-fg-mute">
        当前策略：<span className="font-medium text-fg-soft">{def?.name}</span>（在左侧「我的策略」切换）
      </p>

      {/* 风险 KPI */}
      <StatStrip
        stats={[
          { label: "当前回撤", value: `${(data.currentDrawdown * 100).toFixed(2)}%`, tone: data.currentDrawdown < -0.05 ? "down" : "flat" },
          { label: "VaR (95%)", value: data.var95 == null ? "--" : `${(data.var95 * 100).toFixed(2)}%`, tone: "down" },
          { label: "年化波动率", value: `${(data.volatility * 100).toFixed(1)}%` },
          { label: "Beta (β)", value: data.beta == null ? "--" : data.beta.toFixed(2) },
          { label: "杠杆率", value: `${data.leverage.toFixed(1)}x`, tone: data.leverage > 1.5 ? "accent" : "flat" },
          { label: "触发预警", value: `${triggeredCount} / ${enabledCount}`, tone: triggeredCount > 0 ? "down" : "flat", sub: "已启用规则" },
        ]}
      />

      <div className="grid grid-cols-12 gap-4">
        {/* 回撤事件 */}
        <Card title="回撤事件" en="DRAWDOWN EVENTS" delay={120} pad={false} className="col-span-7">
          <table className="w-full text-xs">
            <thead className="bg-ink-800">
              <tr className="border-b border-line">
                <th className={cn(TH, "pl-5")}>开始</th>
                <th className={TH}>见底</th>
                <th className={TH}>修复</th>
                <th className={cn(TH, "text-right")}>最大回撤</th>
                <th className={cn(TH, "text-right")}>持续天数</th>
                <th className={cn(TH, "pr-5 text-right")}>状态</th>
              </tr>
            </thead>
            <tbody>
              {data.drawdownEvents.map((e, i) => (
                <tr key={i} className="border-b border-line/40 last:border-0 hover:bg-ink-700/50">
                  <td className="num px-4 py-3 pl-5 text-fg-soft">{e.start}</td>
                  <td className="num px-4 py-3 text-fg-soft">{e.trough}</td>
                  <td className="num px-4 py-3 text-fg-soft">{e.recovered ?? "--"}</td>
                  <td className="num px-4 py-3 text-right font-semibold text-down">
                    {(e.depth * 100).toFixed(2)}%
                  </td>
                  <td className="num px-4 py-3 text-right text-fg">{e.durationDays}</td>
                  <td className="px-4 py-3 pr-5 text-right">
                    <span
                      className={cn(
                        "inline-flex rounded-full border px-2 py-0.5 text-[10px] font-medium",
                        e.recovered
                          ? "border-down/30 bg-down/10 text-down"
                          : "border-up/30 bg-up/10 text-up"
                      )}
                    >
                      {e.recovered ? "已修复" : "修复中"}
                    </span>
                  </td>
                </tr>
              ))}
              {data.drawdownEvents.length === 0 && (
                <tr>
                  <td colSpan={6} className="py-10 text-center text-xs text-fg-mute">
                    回测区间内无超过 5% 的回撤事件
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </Card>

        {/* 预警规则 */}
        <Card title="风险预警规则" en="ALERTS" delay={160} pad={false} className="col-span-5">
          <ul className="divide-y divide-line/50">
            {data.alerts.map((a) => {
              const on = enabled[a.id];
              return (
                <li key={a.id} className="flex items-center gap-3 px-5 py-3.5">
                  <span
                    className={cn(
                      "flex h-7 w-7 shrink-0 items-center justify-center rounded-lg",
                      a.triggered && on ? "bg-up/10 text-up" : "bg-down/10 text-down"
                    )}
                  >
                    {a.triggered && on ? <AlertTriangle size={14} /> : <ShieldCheck size={14} />}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-medium text-fg">{a.rule}</p>
                    <p className="num mt-0.5 text-[11px] text-fg-mute">
                      阈值 {a.threshold} · 当前{" "}
                      <span className={a.triggered && on ? "text-up" : "text-fg-soft"}>
                        {a.current}
                      </span>
                    </p>
                  </div>
                  <span
                    className={cn(
                      "rounded-full px-2 py-0.5 text-[10px] font-medium",
                      a.triggered && on ? "bg-up/10 text-up" : "bg-ink-600 text-fg-mute"
                    )}
                  >
                    {a.triggered && on ? "已触发" : "正常"}
                  </span>
                  {/* 开关 */}
                  <button
                    onClick={() => setEnabled((prev) => ({ ...prev, [a.id]: !prev[a.id] }))}
                    className={cn(
                      "relative h-5 w-9 shrink-0 rounded-full transition-colors",
                      on ? "bg-accent/70" : "bg-ink-600"
                    )}
                  >
                    <span
                      className={cn(
                        "absolute top-0.5 h-4 w-4 rounded-full bg-white transition-all",
                        on ? "left-[18px]" : "left-0.5"
                      )}
                    />
                  </button>
                </li>
              );
            })}
          </ul>
        </Card>
      </div>

      {/* 月度收益热力图 */}
      <Card title="月度收益" en="MONTHLY RETURNS" delay={220} pad={false}>
        <div className="p-5">
          <div className="grid gap-1.5" style={{ gridTemplateColumns: "48px repeat(12, 1fr)" }}>
            <span />
            {Array.from({ length: 12 }, (_, i) => (
              <span key={i} className="num pb-1 text-center text-[10px] text-fg-mute">
                {i + 1}月
              </span>
            ))}
            {Object.entries(years).map(([year, months]) => (
              <Fragment key={year}>
                <span className="num flex items-center text-[11px] font-semibold text-fg-soft">
                  {year}
                </span>
                {months.map((m, i) => (
                  <div
                    key={`${year}-${i}`}
                    className="reveal flex h-12 flex-col items-center justify-center rounded-md"
                    style={{
                      background: heatColor(m.ret),
                      animationDelay: `${i * 30}ms`,
                    }}
                    title={`${m.month}　${(m.ret * 100).toFixed(2)}%`}
                  >
                    <span
                      className="num text-[11px] font-semibold"
                      style={{ color: m.ret >= 0 ? "#FDA4AF" : "#6EE7B7" }}
                    >
                      {m.ret >= 0 ? "+" : ""}
                      {(m.ret * 100).toFixed(1)}%
                    </span>
                  </div>
                ))}
                {Array.from({ length: 12 - months.length }, (_, i) => (
                  <span key={`empty-${year}-${i}`} className="h-12 rounded-md bg-ink-700/30" />
                ))}
              </Fragment>
            ))}
          </div>
          <div className="mt-3 flex items-center justify-end gap-4 text-[10px] text-fg-mute">
            <span className="flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-sm" style={{ background: heatColor(0.06) }} />
              盈利
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-sm" style={{ background: heatColor(-0.06) }} />
              亏损
            </span>
            <span>颜色越深幅度越大（±8% 饱和）</span>
          </div>
        </div>
      </Card>
    </main>
  );
}
