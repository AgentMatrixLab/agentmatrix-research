import { Outlet } from "react-router-dom";
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
  return (
    <div className="min-h-screen text-fg">
      <Sidebar />
      <div className="min-w-[1240px] pl-60">
        <Header />
        <Outlet />
      </div>
      <Toast />
    </div>
  );
}
