import { useCallback, useEffect, useRef, useState } from "react";
import {
  CheckCircle2,
  CloudUpload,
  FileCode2,
  FileText,
  Loader2,
  Play,
  XCircle,
} from "lucide-react";
import Card from "@/components/Card";
import { cn } from "@/lib/utils";
import {
  listJobs,
  submitBacktest,
  uploadStrategy,
  type BacktestJob,
  type BenchmarkKey,
} from "@/api";
import { dates } from "@/data/mock";
import { useDashStore } from "@/store/useDashStore";

const STATUS_META: Record<
  BacktestJob["status"],
  { label: string; cls: string; dot: string }
> = {
  queued: { label: "排队中", cls: "border-line bg-ink-700 text-fg-mute", dot: "bg-fg-mute" },
  running: { label: "运行中", cls: "border-accent/30 bg-accent/10 text-accent", dot: "bg-accent animate-pulse-dot" },
  done: { label: "已完成", cls: "border-down/30 bg-down/10 text-down", dot: "bg-down" },
  failed: { label: "失败", cls: "border-up/30 bg-up/10 text-up", dot: "bg-up" },
};

function fmtNow(): string {
  const d = new Date();
  const p = (x: number) => `${x}`.padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

function fmtDuration(ms?: number): string {
  if (!ms) return "--";
  const s = Math.round(ms / 1000);
  return `${Math.floor(s / 60)}m ${s % 60}s`;
}

const INPUT =
  "w-full rounded-lg border border-line bg-ink-900 px-3 py-2 text-xs text-fg outline-none transition-colors focus:border-accent/50";

export default function BacktestCenter() {
  const notify = useDashStore((s) => s.notify);
  const fileInput = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [parseState, setParseState] = useState<"idle" | "parsing" | "ok" | "fail">("idle");
  const [parseMsg, setParseMsg] = useState("");
  const [fileId, setFileId] = useState<string | undefined>();

  const [name, setName] = useState("");
  const [start, setStart] = useState(dates[0]);
  const [end, setEnd] = useState(dates[dates.length - 1]);
  const [capital, setCapital] = useState("1000000");
  const [benchmark, setBenchmark] = useState<BenchmarkKey>("csi300");
  const [feeRate, setFeeRate] = useState("0.00025");
  const [slippage, setSlippage] = useState("0.001");

  const [jobs, setJobs] = useState<BacktestJob[]>([]);

  useEffect(() => {
    listJobs().then(setJobs);
  }, []);

  // 前端模拟任务进度推进（后端接入后由 GET /api/backtests/{id} 轮询替代）
  useEffect(() => {
    const timer = setInterval(() => {
      setJobs((prev) => {
        let hasRunning = prev.some((j) => j.status === "running");
        let promoted = false;
        return prev.map((j) => {
          if (j.status === "running") {
            const next = Math.min(100, j.progress + 1 + Math.random() * 2.5);
            return next >= 100
              ? { ...j, progress: 100, status: "done" as const, durationMs: 120000 + Math.random() * 90000, resultId: `R-${j.id.slice(-3)}` }
              : { ...j, progress: next };
          }
          // 无运行中任务时，队首任务进入运行
          if (!hasRunning && !promoted && j.status === "queued") {
            promoted = true;
            hasRunning = true;
            return { ...j, status: "running" as const, progress: 1 };
          }
          return j;
        });
      });
    }, 1200);
    return () => clearInterval(timer);
  }, []);

  const handleFile = useCallback(
    (f: File) => {
      setFile(f);
      setParseState("parsing");
      setParseMsg("");
      uploadStrategy(f).then((res) => {
        setParseState(res.parsedOk ? "ok" : "fail");
        setParseMsg(res.message);
        if (res.parsedOk) {
          setFileId(res.fileId);
          if (!name) setName(f.name.replace(/\.py$/, ""));
        } else {
          setFileId(undefined);
        }
      });
    },
    [name]
  );

  const startBacktest = () => {
    if (!fileId) {
      notify("请先上传并解析策略文件（.py）");
      return;
    }
    submitBacktest({
      fileId,
      start,
      end,
      capital: Number(capital) || 1000000,
      benchmark,
      feeRate: Number(feeRate) || 0,
      slippage: Number(slippage) || 0,
    }).then(({ jobId }) => {
      setJobs((prev) => [
        {
          id: jobId,
          strategyName: name || file?.name || "未命名策略",
          status: "running",
          progress: 0,
          submittedAt: fmtNow(),
        },
        ...prev,
      ]);
      notify(`回测任务 ${jobId} 已提交`);
    });
  };

  return (
    <main className="mx-auto max-w-[1600px] space-y-4 px-6 py-5">
      <div className="grid grid-cols-12 gap-4">
        {/* 上传策略 */}
        <Card title="上传策略" en="UPLOAD" delay={60} pad={false} className="col-span-5">
          <div className="p-5">
            <input
              ref={fileInput}
              type="file"
              accept=".py"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) handleFile(f);
                e.target.value = "";
              }}
            />
            <button
              onClick={() => fileInput.current?.click()}
              onDragOver={(e) => {
                e.preventDefault();
                setDragOver(true);
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragOver(false);
                const f = e.dataTransfer.files?.[0];
                if (f) handleFile(f);
              }}
              className={cn(
                "flex w-full flex-col items-center gap-3 rounded-xl border border-dashed px-6 py-10 transition-colors",
                dragOver
                  ? "border-accent/60 bg-accent/[0.06]"
                  : "border-line hover:border-accent/40 hover:bg-ink-700/40"
              )}
            >
              <span className="flex h-12 w-12 items-center justify-center rounded-xl bg-accent/10 text-accent">
                <CloudUpload size={22} />
              </span>
              <div className="text-center">
                <p className="text-xs font-medium text-fg">拖拽 .py 文件到此处，或点击选择</p>
                <p className="mt-1 text-[11px] text-fg-mute">单文件 ≤ 1MB · 仅支持 Python 策略</p>
              </div>
            </button>

            {/* 文件解析状态 */}
            {file && (
              <div className="mt-3 flex items-center gap-3 rounded-lg border border-line bg-ink-900 px-3 py-2.5">
                <FileCode2 size={16} className="shrink-0 text-accent" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs font-medium text-fg">{file.name}</p>
                  <p className="num text-[10px] text-fg-mute">{(file.size / 1024).toFixed(1)} KB</p>
                </div>
                {parseState === "parsing" && (
                  <span className="flex items-center gap-1.5 text-[11px] text-fg-mute">
                    <Loader2 size={13} className="animate-spin" />
                    解析中…
                  </span>
                )}
                {parseState === "ok" && (
                  <span className="flex items-center gap-1.5 text-[11px] text-down">
                    <CheckCircle2 size={13} />
                    解析通过
                  </span>
                )}
                {parseState === "fail" && (
                  <span className="flex items-center gap-1.5 text-[11px] text-up">
                    <XCircle size={13} />
                    解析失败
                  </span>
                )}
              </div>
            )}
            {parseMsg && parseState !== "parsing" && (
              <p className={cn("mt-2 text-[11px]", parseState === "ok" ? "text-fg-mute" : "text-up")}>
                {parseMsg}
              </p>
            )}

            {/* 入口约定 */}
            <div className="mt-4 rounded-lg bg-ink-900/70 p-3.5">
              <p className="text-[11px] font-semibold text-fg-soft">策略入口约定</p>
              <pre className="num mt-2 whitespace-pre-wrap text-[11px] leading-relaxed text-fg-mute">
{`def init(context):
    context.s1 = "600519"

def handle_bar(context, data):
    order_target_percent(context.s1, 0.3)`}
              </pre>
            </div>
          </div>
        </Card>

        {/* 回测参数 */}
        <Card title="回测参数" en="PARAMETERS" delay={100} pad={false} className="col-span-7">
          <div className="grid grid-cols-2 gap-4 p-5">
            <label className="col-span-2 block">
              <span className="mb-1.5 block text-[11px] text-fg-mute">策略名称</span>
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder="上传文件后自动填充，可修改" className={INPUT} />
            </label>
            <label className="block">
              <span className="mb-1.5 block text-[11px] text-fg-mute">开始日期</span>
              <input type="date" value={start} onChange={(e) => setStart(e.target.value)} className={cn(INPUT, "num")} />
            </label>
            <label className="block">
              <span className="mb-1.5 block text-[11px] text-fg-mute">结束日期</span>
              <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} className={cn(INPUT, "num")} />
            </label>
            <label className="block">
              <span className="mb-1.5 block text-[11px] text-fg-mute">初始资金（元）</span>
              <input value={capital} onChange={(e) => setCapital(e.target.value)} className={cn(INPUT, "num")} />
            </label>
            <label className="block">
              <span className="mb-1.5 block text-[11px] text-fg-mute">业绩基准</span>
              <select value={benchmark} onChange={(e) => setBenchmark(e.target.value as BenchmarkKey)} className={INPUT}>
                <option value="csi300">沪深300</option>
                <option value="csi500">中证500</option>
                <option value="csi1000">中证1000</option>
              </select>
            </label>
            <label className="block">
              <span className="mb-1.5 block text-[11px] text-fg-mute">手续费率</span>
              <input value={feeRate} onChange={(e) => setFeeRate(e.target.value)} className={cn(INPUT, "num")} />
            </label>
            <label className="block">
              <span className="mb-1.5 block text-[11px] text-fg-mute">滑点</span>
              <input value={slippage} onChange={(e) => setSlippage(e.target.value)} className={cn(INPUT, "num")} />
            </label>
            <div className="col-span-2 flex items-center justify-between border-t border-line/60 pt-4">
              <p className="text-[11px] text-fg-mute">
                提交后任务进入队列，可在下方任务列表跟踪进度
              </p>
              <button
                onClick={startBacktest}
                className="flex items-center gap-1.5 rounded-lg bg-accent px-4 py-2 text-xs font-semibold text-ink-950 shadow-glow transition-all hover:brightness-110"
              >
                <Play size={13} />
                开始回测
              </button>
            </div>
          </div>
        </Card>
      </div>

      {/* 任务列表 */}
      <Card title="回测任务" en="JOBS" delay={160} pad={false}>
        <table className="w-full text-xs">
          <thead className="bg-ink-800">
            <tr className="border-b border-line">
              <th className="px-5 py-2.5 text-left text-[11px] font-medium text-fg-mute">任务 ID</th>
              <th className="px-4 py-2.5 text-left text-[11px] font-medium text-fg-mute">策略</th>
              <th className="px-4 py-2.5 text-left text-[11px] font-medium text-fg-mute">状态</th>
              <th className="w-56 px-4 py-2.5 text-left text-[11px] font-medium text-fg-mute">进度</th>
              <th className="px-4 py-2.5 text-left text-[11px] font-medium text-fg-mute">提交时间</th>
              <th className="px-4 py-2.5 text-right text-[11px] font-medium text-fg-mute">耗时</th>
              <th className="px-5 py-2.5 text-right text-[11px] font-medium text-fg-mute">操作</th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((j) => {
              const meta = STATUS_META[j.status];
              return (
                <tr key={j.id} className="border-b border-line/40 transition-colors last:border-0 hover:bg-ink-700/50">
                  <td className="num px-5 py-3 text-fg-soft">{j.id}</td>
                  <td className="px-4 py-3 font-medium text-fg">{j.strategyName}</td>
                  <td className="px-4 py-3">
                    <span className={cn("inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[10px] font-medium", meta.cls)}>
                      <span className={cn("h-1 w-1 rounded-full", meta.dot)} />
                      {meta.label}
                    </span>
                    {j.status === "failed" && j.error && (
                      <p className="mt-1 max-w-56 truncate text-[10px] text-up/80" title={j.error}>
                        {j.error}
                      </p>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-ink-600">
                        <div
                          className={cn(
                            "h-full rounded-full transition-all duration-500",
                            j.status === "failed" ? "bg-up/70" : "bg-accent"
                          )}
                          style={{ width: `${j.progress}%` }}
                        />
                      </div>
                      <span className="num w-10 text-right text-[11px] text-fg-soft">
                        {Math.floor(j.progress)}%
                      </span>
                    </div>
                  </td>
                  <td className="num px-4 py-3 text-fg-soft">{j.submittedAt}</td>
                  <td className="num px-4 py-3 text-right text-fg-soft">{fmtDuration(j.durationMs)}</td>
                  <td className="px-5 py-3 text-right">
                    <button
                      onClick={() =>
                        notify(j.status === "done" ? "演示环境 · 结果页接入后端后跳转" : "任务尚未完成")
                      }
                      className="text-[11px] text-accent transition-colors hover:brightness-125"
                    >
                      查看结果
                    </button>
                    <button
                      onClick={() => notify("演示环境 · 日志下载稍后接入")}
                      className="ml-3 text-[11px] text-fg-mute transition-colors hover:text-fg"
                    >
                      <FileText size={12} className="inline" /> 日志
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Card>
    </main>
  );
}
