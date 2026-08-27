import { Outlet } from "react-router-dom";
import { useEffect } from "react";
import Sidebar from "./Sidebar";
import Header from "./Header";
import { useDashStore } from "@/store/useDashStore";

/** 全局轻提示：用于暂未开放的按钮点击反馈 */
function Toast() {
  const notice = useDashStore((s) => s.notice);
  if (!notice) return null;
  return (
    <div className="fixed bottom-6 left-1/2 z-50 -translate-x-1/2 rounded-lg border border-accent/30 bg-ink-800/95 px-4 py-2.5 text-xs text-fg shadow-card backdrop-blur reveal">
      {notice}
    </div>
  );
}

export default function Layout() {
  const loadLive = useDashStore((s) => s.loadLive);
  const source = useDashStore((s) => s.source);
  useEffect(() => { loadLive(); }, [loadLive]);
  return (
    <div className="min-h-screen text-fg">
      <Sidebar />
      <div className="min-w-[1240px] pl-60">
        <Header />
        <Outlet />
      </div>
      <Toast />
      <div className={`fixed bottom-4 right-5 z-40 rounded-full border px-3 py-1 text-[10px] ${source === "live" ? "border-down/30 bg-down/10 text-down" : "border-up/30 bg-up/10 text-up"}`}>
        {source === "live" ? "LIVE · AgentMatrix真实结果" : source === "demo" ? "DEMO · 组员保留数据" : "连接真实数据中"}
      </div>
    </div>
  );
}
