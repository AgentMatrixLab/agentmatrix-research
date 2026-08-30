"""Factor DB 静态快照生成器。

把因子目录（metadata 全量因子）导出为 GitHub Pages 可直接加载的静态 JSON
快照，供 pages/factor-db-dashboard 无后端访问。快照与 API 共用同一元数据层
（research_core.factor_db.metadata），保证口径一致。

用法（仓库根目录）：
    python -X utf8 -m research_core.factor_db.snapshot
    python -X utf8 -m research_core.factor_db.snapshot --out pages/factor-db-dashboard/data

输出：
    factors.json  —— 全量因子目录 + 统计（by_category / by_subcategory / by_source）

静态模式说明：因子值实时查询与真实分布需要 Quant API token 与后端服务
（python -m research_core.factor_db.api），静态页面仅提供目录检索、数据字典
与演示分布（正态代理，明确标注，不冒充真实数据）。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from research_core.factor_db.metadata import _all_factors, get_stats

_DEFAULT_OUT = Path("pages/factor-db-dashboard/data")


def build_snapshot() -> dict:
    """构建因子目录快照（与 API /stats、/factors、/dictionary 同口径）。"""
    from research_core.factor_db.metadata import dictionary_rows

    stats = get_stats()
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": "static-snapshot",
        "note": (
            "静态快照模式：目录/检索/数据字典为全量数据；"
            "因子值实时查询与真实分布需本地 API（python -m research_core.factor_db.api）+ Quant API token；"
            "演示分布为正态代理样本，仅展示产品形态，不冒充真实数据。"
        ),
        "stats": stats,
        "factors": list(_all_factors()),
        "dictionary": dictionary_rows(),
    }


def write_snapshot(out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = build_snapshot()
    target = out_dir / "factors.json"
    target.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    size_kb = target.stat().st_size / 1024
    print(f"[factor-db snapshot] factors: {payload['stats']['total_factors']} -> {target} ({size_kb:.0f} KB)")
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Factor DB static snapshot exporter (GitHub Pages)")
    parser.add_argument("--out", type=Path, default=_DEFAULT_OUT, help="输出目录（默认 pages/factor-db-dashboard/data）")
    args = parser.parse_args(argv)

    project_root = Path(__file__).resolve().parents[2]
    out_dir = args.out if args.out.is_absolute() else project_root / args.out
    try:
        write_snapshot(out_dir)
    except Exception as exc:  # pragma: no cover
        print(f"[factor-db snapshot] failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
