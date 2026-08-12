import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, Download, Search } from "lucide-react";
import Card from "@/components/Card";
import StatStrip from "@/components/StatStrip";
import { cn } from "@/lib/utils";
import { listTrades, type TradePage, type TradeRow } from "@/api";
import { fmtMoney } from "@/data/mock";
import { useDashStore } from "@/store/useDashStore";

const PAGE_SIZE = 10;

const TH = "px-4 py-2.5 text-left text-[11px] font-medium text-fg-mute whitespace-nowrap";
const TH_R = cn(TH, "text-right");
const TD = "px-4 py-2.5 whitespace-nowrap";
const TD_R = cn(TD, "num text-right");

type SideFilter = "all" | "buy" | "sell";

export default function Trades() {
  const strategyId = useDashStore((s) => s.strategyId);
  const notify = useDashStore((s) => s.notify);
  const [side, setSide] = useState<SideFilter>("all");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<TradePage | null>(null);
  const [allRows, setAllRows] = useState<TradeRow[]>([]);

  // 汇总统计（全量）
  useEffect(() => {
    listTrades({ strategyId, pageSize: 1000 }).then((res) => setAllRows(res.rows));
  }, [strategyId]);

  // 筛选 + 分页
  useEffect(() => {
    listTrades({
      strategyId,
      side: side === "all" ? undefined : side,
      q: q || undefined,
      page,
      pageSize: PAGE_SIZE,
    }).then(setData);
  }, [strategyId, side, q, page]);

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;
  const buyCount = allRows.filter((t) => t.side === "buy").length;
  const totalAmount = allRows.reduce((a, c) => a + c.amount, 0);
  const totalFee = allRows.reduce((a, c) => a + c.fee, 0);

  return (
    <main className="mx-auto max-w-[1600px] space-y-4 px-6 py-5">
      {/* 汇总条 */}
      <StatStrip
        stats={[
          { label: "成交笔数", value: `${allRows.length}` },
          { label: "成交总金额", value: fmtMoney(totalAmount), tone: "accent" },
          { label: "买入笔数", value: `${buyCount}`, tone: "up", sub: `卖出 ${allRows.length - buyCount} 笔` },
          { label: "总佣金", value: totalFee.toFixed(2), sub: "费率 0.025%" },
        ]}
      />

      <Card
        title="成交明细"
        en="FILLS"
        delay={100}
        pad={false}
        actions={
          <div className="flex items-center gap-2.5">
            {/* 方向筛选 */}
            <div className="flex items-center rounded-lg border border-line bg-ink-900 p-0.5">
              {(
                [
                  { key: "all", label: "全部" },
                  { key: "buy", label: "买入" },
                  { key: "sell", label: "卖出" },
                ] as const
              ).map((t) => (
                <button
                  key={t.key}
                  onClick={() => {
                    setSide(t.key);
                    setPage(1);
                  }}
                  className={cn(
                    "rounded-md px-3 py-1 text-[11px] font-medium transition-all",
                    side === t.key
                      ? t.key === "sell"
                        ? "bg-down/15 text-down"
                        : t.key === "buy"
                          ? "bg-up/15 text-up"
                          : "bg-accent/15 text-accent"
                      : "text-fg-mute hover:text-fg-soft"
                  )}
                >
                  {t.label}
                </button>
              ))}
            </div>

            {/* 搜索 */}
            <div className="relative">
              <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-fg-mute" />
              <input
                value={q}
                onChange={(e) => {
                  setQ(e.target.value);
                  setPage(1);
                }}
                placeholder="代码 / 名称"
                className="w-40 rounded-lg border border-line bg-ink-900 py-1.5 pl-8 pr-3 text-xs text-fg outline-none transition-colors placeholder:text-fg-mute focus:border-accent/50"
              />
            </div>

            <button
              onClick={() => notify("演示环境 · 导出 CSV 稍后接入")}
              className="flex items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-[11px] text-fg-soft transition-colors hover:border-accent/30 hover:text-fg"
            >
              <Download size={13} />
              导出
            </button>
          </div>
        }
      >
        <table className="w-full text-xs">
          <thead className="bg-ink-800">
            <tr className="border-b border-line">
              <th className={cn(TH, "pl-5")}>时间</th>
              <th className={TH}>代码 / 名称</th>
              <th className={TH}>方向</th>
              <th className={TH_R}>成交价</th>
              <th className={TH_R}>数量</th>
              <th className={TH_R}>金额</th>
              <th className={cn(TH_R, "pr-5")}>佣金</th>
            </tr>
          </thead>
          <tbody>
            {(data?.rows ?? []).map((t, i) => (
              <tr key={i} className="border-b border-line/40 transition-colors last:border-0 hover:bg-ink-700/50">
                <td className={cn(TD, "num pl-5 text-fg-soft")}>{t.time}</td>
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
                <td className={cn(TD_R, "pr-5 text-fg-mute")}>{t.fee.toFixed(2)}</td>
              </tr>
            ))}
            {data && data.rows.length === 0 && (
              <tr>
                <td colSpan={7} className="py-10 text-center text-xs text-fg-mute">
                  无匹配成交记录
                </td>
              </tr>
            )}
          </tbody>
        </table>

        {/* 分页器 */}
        <div className="flex items-center justify-between border-t border-line px-5 py-3">
          <p className="num text-[11px] text-fg-mute">
            共 {data?.total ?? 0} 条 · 第 {page} / {totalPages} 页
          </p>
          <div className="flex items-center gap-1.5">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page <= 1}
              className="rounded-md border border-line p-1.5 text-fg-soft transition-colors hover:border-accent/30 hover:text-fg disabled:opacity-30"
            >
              <ChevronLeft size={14} />
            </button>
            {Array.from({ length: totalPages }, (_, i) => i + 1)
              .slice(0, 5)
              .map((p) => (
                <button
                  key={p}
                  onClick={() => setPage(p)}
                  className={cn(
                    "num h-7 w-7 rounded-md text-[11px] transition-colors",
                    p === page
                      ? "bg-accent/15 font-semibold text-accent"
                      : "text-fg-mute hover:bg-ink-700 hover:text-fg"
                  )}
                >
                  {p}
                </button>
              ))}
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages}
              className="rounded-md border border-line p-1.5 text-fg-soft transition-colors hover:border-accent/30 hover:text-fg disabled:opacity-30"
            >
              <ChevronRight size={14} />
            </button>
          </div>
        </div>
      </Card>
    </main>
  );
}
