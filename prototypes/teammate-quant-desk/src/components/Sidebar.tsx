import {
  Activity,
  ArrowLeftRight,
  FlaskConical,
  LayoutDashboard,
  Layers,
  PieChart,
  Settings,
  ShieldAlert,
} from "lucide-react";
import { NavLink } from "react-router-dom";
import { cn } from "@/lib/utils";
import { STRATEGIES, strategyDataMap, type StrategyDef } from "@/data/mock";
import { useDashStore } from "@/store/useDashStore";
import { liveDefinition } from "@/data/live";

const NAV = [
  { icon: LayoutDashboard, label: "策略总览", to: "/" },
  { icon: Layers, label: "组合策略", to: "/portfolio" },
  { icon: PieChart, label: "持仓分析", to: "/positions" },
  { icon: ArrowLeftRight, label: "交易记录", to: "/trades" },
  { icon: ShieldAlert, label: "风险监控", to: "/risk" },
  { icon: FlaskConical, label: "回测中心", to: "/backtest" },
];

function Spark({ data, tone }: { data: number[]; tone: "up" | "down" }) {
  const w = 60;
  const h = 22;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const pts = data
    .map(
      (v, i) =>
        `${((i / (data.length - 1)) * w).toFixed(1)},${(
          h -
          ((v - min) / range) * (h - 3) -
          1.5
        ).toFixed(1)}`
    )
    .join(" ");
  const color = tone === "up" ? "#F43F5E" : "#10B981";
  return (
    <svg width={w} height={h} className="shrink-0 opacity-90">
      <polyline
        points={pts}
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}

function StrategyItem({ def }: { def: StrategyDef }) {
  const strategyId = useDashStore((s) => s.strategyId);
  const setStrategy = useDashStore((s) => s.setStrategy);
  const active = def.id === strategyId;
  const detail = useDashStore((s) => s.details[def.id]);
  const mockData = strategyDataMap[def.id];
  const sparkData = detail?.equity_curve?.slice(-22).map(p => p.nav) || mockData?.spark || [1, 1];
  const today = sparkData.length > 1 ? sparkData.at(-1)! / sparkData.at(-2)! - 1 : 0;
  const up = today >= 0;

  return (
    <button
      onClick={() => setStrategy(def.id)}
      className={cn(
        "group flex w-full items-center gap-3 rounded-lg border px-3 py-2.5 text-left transition-colors",
        active
          ? "border-accent/30 bg-accent/[0.06]"
          : "border-transparent hover:border-line hover:bg-ink-700"
      )}
    >
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <p
            className={cn(
              "truncate text-xs font-medium",
              active ? "text-fg" : "text-fg-soft group-hover:text-fg"
            )}
          >
            {def.name}
          </p>
          {def.status === "paused" && (
            <span className="shrink-0 rounded bg-ink-600 px-1 py-px text-[9px] text-fg-mute">
              暂停
            </span>
          )}
        </div>
        <p className="mt-0.5 text-[10px] text-fg-mute">{def.tag}</p>
      </div>
      <Spark data={sparkData} tone={up ? "up" : "down"} />
      <span className={cn("num w-14 text-right text-xs font-semibold", up ? "text-up" : "text-down")}>
        {up ? "+" : ""}
        {(today * 100).toFixed(2)}%
      </span>
    </button>
  );
}

export default function Sidebar() {
  const notify = useDashStore((s) => s.notify);
  const live = useDashStore((s) => s.strategies);
  const source = useDashStore((s) => s.source);
  const defs = source === "live" ? live.map(liveDefinition) : STRATEGIES;

  return (
    <aside className="fixed inset-y-0 left-0 z-30 flex w-60 flex-col border-r border-line bg-ink-900/90 backdrop-blur">
      {/* 品牌区 */}
      <NavLink to="/" className="flex items-center gap-3 px-5 pb-5 pt-6">
        <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent/15 text-accent shadow-glow">
          <Activity size={18} strokeWidth={2.2} />
        </span>
        <div>
          <p className="text-sm font-extrabold tracking-[0.14em] text-fg">
            QUANT<span className="text-accent">·</span>DESK
          </p>
          <p className="mt-0.5 text-[10px] tracking-[0.2em] text-fg-mute">量化策略面板</p>
        </div>
      </NavLink>

      {/* 主导航 */}
      <nav className="space-y-1 px-3">
        {NAV.map((item) => (
          <NavLink
            key={item.label}
            to={item.to}
            end={item.to === "/"}
            className={({ isActive }) =>
              cn(
                "group flex w-full items-center gap-3 rounded-lg px-3 py-2 text-[13px] transition-colors",
                isActive
                  ? "bg-ink-700 font-semibold text-fg"
                  : "text-fg-soft hover:bg-ink-700/60 hover:text-fg"
              )
            }
          >
            {({ isActive }) => (
              <>
                <item.icon
                  size={16}
                  className={cn(isActive ? "text-accent" : "text-fg-mute group-hover:text-accent")}
                />
                {item.label}
                {isActive && <span className="ml-auto h-1.5 w-1.5 rounded-full bg-accent" />}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* 策略列表 */}
      <div className="mt-6 flex-1 overflow-y-auto px-3 scroll-slim">
        <p className="px-3 pb-2 text-[10px] font-semibold uppercase tracking-[0.2em] text-fg-mute">
          我的策略 · {defs.length}
        </p>
        <div className="space-y-1.5">
          {defs.map((def) => (
            <StrategyItem key={def.id} def={def} />
          ))}
        </div>
      </div>

      {/* 底部状态 */}
      <div className="border-t border-line px-5 py-4">
        <div className="flex items-center gap-2 text-[11px] text-fg-soft">
          <span className="h-1.5 w-1.5 animate-pulse-dot rounded-full bg-down" />
          实盘引擎运行中
          <span className="num ml-auto text-fg-mute">v2.4.1</span>
        </div>
        <button
          onClick={() => notify("演示环境 · 偏好设置稍后接入")}
          className="mt-3 flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-[12px] text-fg-mute transition-colors hover:text-fg"
        >
          <Settings size={14} />
          偏好设置
        </button>
      </div>
    </aside>
  );
}
