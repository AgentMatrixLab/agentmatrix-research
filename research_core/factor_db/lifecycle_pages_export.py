"""导出生命周期面板静态快照到 pages/lifecycle-dashboard/（GitHub Pages 部署）。

Pages 无法运行 Flask 后端，因此把面板做成双模式：
- 动态（本地开发）：前端 fetch /api/factor-db/lifecycle/*
- 静态（GitHub Pages）：导出时把 overview/factors/evidence/单因子详情
  全量冻结为 ./data/*.json，前端读本地 JSON。

用法（仓库根目录）：
    python -X utf8 -m research_core.factor_db.lifecycle_pages_export

前提：runtime/lifecycle/ 下已有 g2_skeleton_report.json
（先运行 python -X utf8 -m research_core.factor_db.g2_skeleton_run）。
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

from common.paths import REPO_ROOT

from research_core.factor_db import lifecycle_service as svc

SRC_DIR = REPO_ROOT / "frontend" / "lifecycle-dashboard"
OUT_DIR = REPO_ROOT / "pages" / "lifecycle-dashboard"

# 文件名安全字符（QAPI33 id 均为标识符，此处兜底）
_SAFE = re.compile(r"[^A-Za-z0-9._-]")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _patch_index(html: str) -> str:
    """注入静态模式开关 + 标注快照性质。源 HTML 导航已用相对 Pages 路径。"""
    html = html.replace(
        '<script src="app.js"></script>',
        "<script>window.LIFECYCLE_STATIC = true;</script>\n  "
        '<script src="app.js"></script>',
    )
    html = html.replace(
        "id=\"sub-title\">从出生到死亡 · 全流程闸门 · 证据链 · OOS 封存<",
        "id=\"sub-title\">从出生到死亡 · 全流程闸门 · 证据链 · OOS 封存（静态快照）<",
    )
    return html


def export() -> dict[str, int]:
    """执行导出，返回统计。前置数据缺失时抛 LifecycleDataError。"""
    if not (SRC_DIR / "app.js").exists():
        raise FileNotFoundError(f"面板源文件缺失：{SRC_DIR}")

    # 先跑一遍数据服务，缺失 runtime 产物会在此抛错
    overview = svc.overview()
    rows = svc.factor_rows()

    # 1) 前端三件套
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True)
    shutil.copy2(SRC_DIR / "styles.css", OUT_DIR / "styles.css")
    shutil.copy2(SRC_DIR / "app.js", OUT_DIR / "app.js")
    (OUT_DIR / "index.html").write_text(
        _patch_index((SRC_DIR / "index.html").read_text(encoding="utf-8")),
        encoding="utf-8",
    )

    # 2) 数据快照
    data_dir = OUT_DIR / "data"
    _write_json(data_dir / "overview.json", overview)
    _write_json(
        data_dir / "factors.json",
        {"count": len(rows), "factors": rows},
    )
    _write_json(
        data_dir / "evidence.json",
        {"events": svc.evidence_feed(200)},
    )
    # 衰减监控 + SLA 通知（可选：先跑 lifecycle_monitor 生成；缺失导出空占位）
    monitor = svc.monitor_report()
    _write_json(
        data_dir / "monitor.json",
        monitor if monitor is not None else {"available": False, "notifications": []},
    )
    for row in rows:
        fid = row["factor_id"]
        detail = svc.factor_detail(fid)
        safe = _SAFE.sub("_", fid)
        _write_json(data_dir / "factors" / f"{safe}.json", detail)

    return {
        "factors": len(rows),
        "files": sum(1 for _ in OUT_DIR.rglob("*") if _.is_file()),
    }


def main() -> None:
    stats = export()
    print(f"[pages-export] {OUT_DIR.relative_to(REPO_ROOT)}")
    print(
        f"[pages-export] {stats['factors']} 个因子 · {stats['files']} 个文件"
        "（含逐因子详情 JSON）"
    )


if __name__ == "__main__":
    main()
