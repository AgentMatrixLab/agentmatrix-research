from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def build_master_report(
    *,
    accuracy_report: dict[str, Any],
    effectiveness_report: dict[str, Any],
    artifacts: dict[str, str],
    output_dir: str | Path,
) -> dict[str, Any]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "accuracy": accuracy_report,
        "effectiveness": effectiveness_report,
        "artifacts": artifacts,
    }
    json_path = output_dir / "alpha158_master_report.json"
    md_path = output_dir / "alpha158_master_report.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Alpha158 前10因子研究总报告",
        "",
        "## 复现精度",
        f"- 对照区间: {accuracy_report.get('overlap_start')} ~ {accuracy_report.get('overlap_end')}",
        f"- 总体状态: **{accuracy_report.get('overall_status')}**",
        f"- 通过因子数: {accuracy_report.get('passed_count')} / {len(accuracy_report.get('factors', []))}",
        "",
        "## 有效性摘要",
    ]
    factor_metrics = effectiveness_report.get("factor_metrics", {})
    if isinstance(factor_metrics, dict) and "metrics" in factor_metrics:
        factor_metrics = factor_metrics["metrics"]
    for factor, metrics in factor_metrics.items():
        if not isinstance(metrics, dict):
            continue
        lines.append(
            f"- `{factor}`: rank_ic_mean={metrics.get('rank_ic_mean')}, "
            f"rank_ic_ir={metrics.get('rank_ic_ir')}, coverage={metrics.get('coverage_ratio')}"
        )
    lines.extend(["", "## 产物路径"])
    for key, value in artifacts.items():
        lines.append(f"- {key}: `{value}`")

    md_path.write_text("\n".join(lines), encoding="utf-8")
    payload["json_path"] = str(json_path.resolve())
    payload["markdown_path"] = str(md_path.resolve())
    return payload