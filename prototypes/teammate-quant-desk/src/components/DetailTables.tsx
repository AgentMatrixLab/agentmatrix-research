import { useState } from "react";
import Card from "./Card";
import HoldingsTable from "./HoldingsTable";
import { fmtMoney, type Trade } from "@/data/mock";
import { useDashboard } from "@/hooks/useDashboard";
import { cn } from "@/lib/utils";

type Tab = "holdings" | "trades";

const TH = "px-4 py-2.5 text-left text-[11px] font-medium text-fg-mute whitespace-nowrap";
const TH_R = cn(TH, "text-right");
const TD = "px-4 py-2.5 whitespace-nowrap";
const TD_R = cn(TD, "num text-right");

function TradesTable({ trades }: { trades: Trade[] }) {
  return (
    <table className="w-full text-xs">
      <thead className="sticky top-0 z-10 bg-ink-800">
        <tr className="border-b border-line">
          <th className={TH}>时间</th>
          <th className={TH}>代码 / 名称</th>
          <th className={TH}>方向</th>
          <th className={TH_R}>成交价</th>
          <th className={TH_R}>数量</th>
          <th className={TH_R}>金额</th>
          <th className={TH_R}>佣金</th>
        </tr>
      </thead>
      <tbody>
        {trades.slice(0, 14).map((t, i) => (
          <tr key={i} className="border-b border-line/40 transition-colors last:border-0 hover:bg-ink-700/50">
            <td className={cn(TD, "num text-fg-soft")}>{t.time}</td>
            <td className={TD}>
              <span className="num text-fg-mute">{t.code}</span>
              <span className="ml-2 font-medium text-fg">{t.name}</span>
            </td>
            <td className={TD}>
              <span
                className={cn(
                  "inline-flex w-12 justify-center rounded border px-1.5 py-0.5 text-[11px] font-semibold",
                  t.side === "buy"
                    ? "border-up/25 bg-up/10 text-up"
                    : "border-down/25 bg-down/10 text-down"
                )}
              >
                {t.side === "buy" ? "买入" : "卖出"}
              </span>
            </td>
            <td className={cn(TD_R, "text-fg")}>{t.price.toFixed(2)}</td>
            <td className={TD_R}>{t.qty.toLocaleString()}</td>
            <td className={TD_R}>{fmtMoney(t.amount)}</td>
            <td className={cn(TD_R, "text-fg-mute")}>{t.fee.toFixed(2)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function DetailTables() {
  const [tab, setTab] = useState<Tab>("holdings");
  const { holdings, trades } = useDashboard();

  return (
    <Card
      title={tab === "holdings" ? "持仓明细" : "交易明细"}
      en={tab === "holdings" ? "POSITIONS" : "TRADES"}
      delay={300}
      pad={false}
      actions={
        <div className="flex items-center rounded-lg border border-line bg-ink-900 p-0.5">
          {(
            [
              { key: "holdings", label: "持仓明细", count: holdings.length },
              { key: "trades", label: "交易明细", count: trades.length },
            ] as const
          ).map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={cn(
                "flex items-center gap-1.5 rounded-md px-3 py-1 text-[11px] font-medium transition-all",
                tab === t.key ? "bg-accent/15 text-accent" : "text-fg-mute hover:text-fg-soft"
              )}
            >
              {t.label}
              <span className="num text-[10px] opacity-70">{t.count}</span>
            </button>
          ))}
        </div>
      }
    >
      <div className="scroll-slim max-h-[380px] overflow-auto">
        {tab === "holdings" ? <HoldingsTable holdings={holdings} /> : <TradesTable trades={trades} />}
      </div>
    </Card>
  );
}
