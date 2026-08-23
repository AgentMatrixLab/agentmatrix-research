import KpiStrip from "@/components/KpiStrip";
import NavChart from "@/components/NavChart";
import MetricsGrid from "@/components/MetricsGrid";
import DetailTables from "@/components/DetailTables";
import PortfolioPanel from "@/components/PortfolioPanel";
import FolioSection from "@/components/FolioSection";

export default function Home() {
  return (
    <main className="mx-auto max-w-[1600px] space-y-4 px-6 py-5">
      {/* 策略组合：Top5 逆波动率加权（自动计算） */}
      <FolioSection />

      {/* 个体策略详情（侧边栏点击切换） */}
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
        <span className="num">数据更新于 2026-07-28 15:00 CST · 演示数据</span>
      </footer>
    </main>
  );
}
