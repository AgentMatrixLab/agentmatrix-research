import { useMemo } from "react";
import ReactECharts from "echarts-for-react";
import Card from "./Card";
import { buildNavOption } from "./charts/navOption";
import { useDashboard } from "@/hooks/useDashboard";

function Legend({ benchName }: { benchName: string }) {
  return (
    <div className="flex shrink-0 items-center gap-4 whitespace-nowrap text-[11px] text-fg-soft">
      <span className="flex items-center gap-1.5">
        <span className="h-[3px] w-4 rounded-full bg-accent" />
        策略净值
      </span>
      <span className="flex items-center gap-1.5">
        <span className="h-0 w-4 border-t border-dashed border-slate-500" />
        {benchName}
      </span>
      <span className="flex items-center gap-1.5">
        <span className="h-[3px] w-4 rounded-full bg-up" />
        回撤
      </span>
    </div>
  );
}

export default function NavChart({ className }: { className?: string }) {
  const { points, bench, period } = useDashboard();
  const option = useMemo(() => buildNavOption(points, bench.name), [points, bench.name]);
  const last = points[points.length - 1];

  return (
    <Card
      title="净值表现"
      en="NET VALUE / DRAWDOWN"
      delay={120}
      pad={false}
      className={className}
      actions={<Legend benchName={bench.name} />}
      bodyClassName="flex flex-col"
    >
      <div className="flex items-baseline gap-3 px-5 pt-4">
        <span className="num text-2xl font-bold text-fg">{last.strategy.toFixed(4)}</span>
        <span className={last.ret >= 0 ? "num text-xs font-semibold text-up" : "num text-xs font-semibold text-down"}>
          {last.ret >= 0 ? "+" : ""}
          {(last.ret * 100).toFixed(2)}% 今日
        </span>
        <span className="num ml-auto text-[11px] text-fg-mute">区间 {period}</span>
      </div>
      <div className="h-[430px] w-full">
        <ReactECharts
          option={option}
          notMerge
          style={{ height: "100%", width: "100%" }}
        />
      </div>
    </Card>
  );
}
