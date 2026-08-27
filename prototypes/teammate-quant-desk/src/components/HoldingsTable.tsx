import { fmtMoney } from "@/data/mock";
import { cn } from "@/lib/utils";

/** 兼容 Holding 与 API PositionRow 的最小行结构 */
export interface HoldingsRow {
  code: string;
  name: string;
  industry?: string;
  qty: number;
  cost: number;
  price: number;
  value: number;
  pnl: number;
  pnlPct: number;
  weight: number;
}

const TH = "px-4 py-2.5 text-left text-[11px] font-medium text-fg-mute whitespace-nowrap";
const TH_R = cn(TH, "text-right");
const TD = "px-4 py-2.5 whitespace-nowrap";
const TD_R = cn(TD, "num text-right");

function pnlTone(v: number) {
  return v >= 0 ? "text-up" : "text-down";
}

/** 持仓明细表：策略总览与持仓分析页共用 */
export default function HoldingsTable({
  holdings,
  showIndustry = false,
}: {
  holdings: HoldingsRow[];
  showIndustry?: boolean;
}) {
  return (
    <table className="w-full text-xs">
      <thead className="sticky top-0 z-10 bg-ink-800">
        <tr className="border-b border-line">
          <th className={TH}>代码 / 名称</th>
          {showIndustry && <th className={TH}>行业</th>}
          <th className={TH_R}>持仓量</th>
          <th className={TH_R}>成本价</th>
          <th className={TH_R}>现价</th>
          <th className={TH_R}>市值</th>
          <th className={TH_R}>浮动盈亏</th>
          <th className={TH_R}>盈亏 %</th>
          <th className={cn(TH, "w-36")}>仓位占比</th>
        </tr>
      </thead>
      <tbody>
        {holdings.map((h) => (
          <tr
            key={h.code}
            className="border-b border-line/40 transition-colors last:border-0 hover:bg-ink-700/50"
          >
            <td className={TD}>
              <span className="num text-fg-mute">{h.code}</span>
              <span className="ml-2 font-medium text-fg">{h.name}</span>
            </td>
            {showIndustry && (
              <td className={TD}>
                <span className="rounded border border-line bg-ink-700 px-1.5 py-0.5 text-[10px] text-fg-soft">
                  {h.industry}
                </span>
              </td>
            )}
            <td className={TD_R}>{h.qty.toLocaleString()}</td>
            <td className={TD_R}>{h.cost.toFixed(2)}</td>
            <td className={cn(TD_R, "text-fg")}>{h.price.toFixed(2)}</td>
            <td className={TD_R}>{fmtMoney(h.value)}</td>
            <td className={cn(TD_R, "font-semibold", pnlTone(h.pnl))}>
              {h.pnl >= 0 ? "+" : ""}
              {fmtMoney(h.pnl)}
            </td>
            <td className={cn(TD_R, "font-semibold", pnlTone(h.pnlPct))}>
              {h.pnlPct >= 0 ? "+" : ""}
              {(h.pnlPct * 100).toFixed(2)}%
            </td>
            <td className={TD}>
              <div className="flex items-center gap-2">
                <div className="h-1 flex-1 overflow-hidden rounded-full bg-ink-600">
                  <div
                    className="h-full rounded-full bg-accent/70"
                    style={{ width: `${Math.min(h.weight * 100, 100)}%` }}
                  />
                </div>
                <span className="num w-12 text-right text-fg-soft">
                  {(h.weight * 100).toFixed(1)}%
                </span>
              </div>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
