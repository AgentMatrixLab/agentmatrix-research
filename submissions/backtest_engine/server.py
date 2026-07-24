"""
本地回测报告服务器 — http://localhost:8080

用法:
  python server.py              # 前台运行
  python server.py --bg         # 后台运行 (Windows)
"""
import os, sys, subprocess, argparse, glob, json
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from config import RESULTS_DIR, BASE_DIR


class ReportHandler(SimpleHTTPRequestHandler):
    """自动跳转到最新报告"""

    def do_GET(self):
        parsed = urlparse(self.path)

        # 根路径 → 最新报告
        if parsed.path == "/" or parsed.path == "":
            latest = self._find_latest()
            if latest:
                self.send_response(302)
                self.send_header("Location", f"/{latest}")
                self.end_headers()
                return
            # 没有报告 → 显示目录列表
            super().do_GET()
            return

        super().do_GET()

    def _find_latest(self):
        """找最新的结果目录"""
        results_dir = os.path.join(os.getcwd(), "results")
        if not os.path.exists(results_dir):
            return None
        # 优先用 latest (模拟/实时更新)
        latest_link = os.path.join(results_dir, "latest", "report.html")
        if os.path.exists(latest_link):
            return "results/latest/report.html"
        # 否则找最新的日期目录
        dirs = sorted(glob.glob(os.path.join(results_dir, "20*")))
        latest = os.path.basename(dirs[-1]) if dirs else None
        if latest:
            return f"results/{latest}/report.html"
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8080, help="端口")
    parser.add_argument("--bg", action="store_true", help="后台运行")
    args = parser.parse_args()

    # 切换到项目目录
    os.chdir(BASE_DIR)
    print(f"报告服务器: http://localhost:{args.port}")
    print(f"  根目录: {BASE_DIR}")
    print(f"  按 Ctrl+C 停止")

    if args.bg:
        # Windows 后台
        subprocess.Popen(
            [sys.executable, __file__, "--port", str(args.port)],
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
        print("  已在后台启动")
        return

    server = HTTPServer(("0.0.0.0", args.port), ReportHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
        server.server_close()


if __name__ == "__main__":
    main()
