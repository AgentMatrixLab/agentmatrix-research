import { Bell, Check, ChevronDown, Search } from "lucide-react";
import { useState } from "react";
import { useLocation } from "react-router-dom";
import { cn } from "@/lib/utils";
import { BENCHMARKS, PERIODS } from "@/data/mock";
import { useDashStore } from "@/store/useDashStore";
import { useDashboard } from "@/hooks/useDashboard";

const ROUTE_META: Record<string, { title: string; subtitle: string }> = {
  "/portfolio": { title: "组合策略", subtitle: "自选策略组合 · 一键组合回测" },
  "/backtest": { title: "回测中心", subtitle: "上传策略文件 · 自动执行回测" },
  "/positions": { title: "持仓分析", subtitle: "持仓结构 · 行业与风格分布" },
  "/trades": { title: "交易记录", subtitle: "全量成交明细 · 筛选与导出" },
  "/risk": { title: "风险监控", subtitle: "预警规则 · 回撤事件 · 月度收益" },
};

export default function Header() {
  const { def, bench } = useDashboard();
  const period = useDashStore((s) => s.period);
  const setPeriod = useDashStore((s) => s.setPeriod);
  const setBenchmark = useDashStore((s) => s.setBenchmark);
  const notify = useDashStore((s) => s.notify);
  const [benchOpen, setBenchOpen] = useState(false);
  const location = useLocation();

  const isHome = location.pathname === "/";
  const meta = ROUTE_META[location.pathname];
  const running = def.status === "running";
  const { points } = useDashboard();

  return (
    <header className="sticky top-0 z-20 border-b border-line bg-ink-950/80 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-[1600px] items-center gap-4 px-6">
        {isHome ? (
          /* 策略总览：当前策略 */
          <div className="min-w-0">
            <div className="flex items-center gap-2.5">
              <h1 className="truncate text-[15px] font-bold tracking-wide text-fg">
                {def.name}
              </h1>
              <span className="num text-[10px] text-fg-mute">{def.version}</span>
              <span
                className={cn(
                  "flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[10px] font-medium",
                  running
                    ? "border-down/30 bg-down/10 text-down"
                    : "border-line bg-ink-700 text-fg-mute"
                )}
              >
                <span
                  className={cn(
                    "h-1 w-1 rounded-full",
                    running ? "animate-pulse-dot bg-down" : "bg-fg-mute"
                  )}
                />
                {running ? "运行中" : "已暂停"}
              </span>
            </div>
            <p className="mt-0.5 text-[11px] text-fg-mute">
              回测区间 {points[0]?.date || "--"} ~ {points.at(-1)?.date || "--"} · 基准 {bench.name}
            </p>
          </div>
        ) : (
          /* 其他页面：页面标题 */
          <div className="min-w-0">
            <h1 className="truncate text-[15px] font-bold tracking-wide text-fg">
              {meta?.title ?? "策略总览"}
            </h1>
            <p className="mt-0.5 text-[11px] text-fg-mute">{meta?.subtitle}</p>
          </div>
        )}

        <div className="ml-auto flex items-center gap-3">
          {isHome && (
            <>
              {/* 周期切换 */}
              <div className="flex items-center rounded-lg border border-line bg-ink-800 p-1">
                {PERIODS.map((p) => (
                  <button
                    key={p}
                    onClick={() => setPeriod(p)}
                    className={cn(
                      "num rounded-md px-2.5 py-1 text-[11px] font-semibold transition-all",
                      period === p
                        ? "bg-accent/15 text-accent shadow-glow"
                        : "text-fg-mute hover:text-fg-soft"
                    )}
                  >
                    {p}
                  </button>
                ))}
              </div>

              {/* 基准选择 */}
              <div className="relative">
                <button
                  onClick={() => setBenchOpen((v) => !v)}
                  className={cn(
                    "flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs transition-colors",
                    benchOpen
                      ? "border-accent/40 text-fg"
                      : "border-line bg-ink-800 text-fg-soft hover:border-accent/30 hover:text-fg"
                  )}
                >
                  {bench.name}
                  <ChevronDown
                    size={13}
                    className={cn("text-fg-mute transition-transform", benchOpen && "rotate-180")}
                  />
                </button>
                {benchOpen && (
                  <>
                    <div className="fixed inset-0 z-10" onClick={() => setBenchOpen(false)} />
                    <ul className="absolute right-0 z-20 mt-1.5 w-36 overflow-hidden rounded-lg border border-line bg-ink-800 py-1 shadow-card">
                      {BENCHMARKS.map((b) => (
                        <li key={b.key}>
                          <button
                            onClick={() => {
                              setBenchmark(b.key);
                              setBenchOpen(false);
                            }}
                            className={cn(
                              "flex w-full items-center justify-between px-3 py-2 text-xs transition-colors",
                              b.key === bench.key
                                ? "bg-accent/10 text-accent"
                                : "text-fg-soft hover:bg-ink-700 hover:text-fg"
                            )}
                          >
                            {b.name}
                            {b.key === bench.key && <Check size={13} />}
                          </button>
                        </li>
                      ))}
                    </ul>
                  </>
                )}
              </div>

              <span className="h-5 w-px bg-line" />
            </>
          )}

          {/* 搜索 / 通知 / 用户 */}
          <button
            onClick={() => notify("演示环境 · 全局搜索稍后接入")}
            className="rounded-lg p-2 text-fg-mute transition-colors hover:bg-ink-700 hover:text-fg"
          >
            <Search size={16} />
          </button>
          <button
            onClick={() => notify("暂无新通知")}
            className="relative rounded-lg p-2 text-fg-mute transition-colors hover:bg-ink-700 hover:text-fg"
          >
            <Bell size={16} />
            <span className="absolute right-1.5 top-1.5 h-1.5 w-1.5 rounded-full bg-up" />
          </button>
          <button
            onClick={() => notify("演示环境 · 账户中心稍后接入")}
            className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-accent/80 to-cyan-900 text-[11px] font-bold text-ink-950 transition-transform hover:scale-105"
          >
            TR
          </button>
        </div>
      </div>
    </header>
  );
}
