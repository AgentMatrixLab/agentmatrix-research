import KpiStrip from "@/components/KpiStrip";
import NavChart from "@/components/NavChart";
import MetricsGrid from "@/components/MetricsGrid";
import DetailTables from "@/components/DetailTables";
import PortfolioPanel from "@/components/PortfolioPanel";
import { useDashStore } from "@/store/useDashStore";

export default function Home() {
  const source = useDashStore(s => s.source);
  const details = useDashStore(s => s.details);
  const latest = Object.values(details).map(d=>d.updated_at).filter(Boolean).sort().at(-1);
  return (
    <main className="mx-auto max-w-[1600px] space-y-4 px-6 py-5">
      {/* 第一视觉焦点：核心指标 */}
      <KpiStrip />

      {/* 视觉中心：净值+回撤主图，右侧组合策略 */}
      <div className="grid grid-cols-12 gap-4">
        <NavChart className="col-span-8" />
        <PortfolioPanel className="col-span-4" />
      </div>

      {/* 指标明细 */}
      <MetricsGrid />

      {/* 持仓 / 交易明细 */}
      <DetailTables />

      <footer className="flex items-center justify-between px-1 pb-4 pt-2 text-[11px] text-fg-mute">
        <span>
          QUANT<span className="text-accent">·</span>DESK 量化策略面板
        </span>
        <span className="num">{source === "live" ? `真实结果更新于 ${latest || "--"}` : "本地演示回退数据"}</span>
      </footer>
    </main>
  );
}
