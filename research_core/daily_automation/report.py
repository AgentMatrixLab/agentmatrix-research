"""Daily report generator for AGE-8 — human-readable markdown of the day's run."""

from __future__ import annotations

from datetime import datetime
from typing import Any


def build_daily_report(
    report_date: str,
    update: dict[str, Any],
    coverage: dict[str, Any],
    mining: dict[str, Any],
) -> str:
    lines: list[str] = []
    lines.append(f"# 每日因子系统日报 — {report_date}")
    lines.append("")
    lines.append(f"生成时间: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}  |  AgentMatrixLab · AGE-8")
    lines.append("")

    # 1. Data update
    lines.append("## 1. 数据更新")
    lines.append("")
    if update.get("skipped"):
        lines.append("- 更新: 跳过（--skip-update）")
    else:
        lines.append(f"- 股票池: CSI300 ({update.get('attempted', 0)} 只)")
        lines.append(f"- 成功: {update.get('ok', 0)} / 失败: {update.get('failed', 0)}")
        lines.append(f"- 新增/更新行数: {update.get('rows_upserted', 0)}")
        lines.append(f"- 窗口: {update.get('window', {}).get('start')} ~ {update.get('window', {}).get('end')}")
        lines.append(f"- 耗时: {update.get('elapsed_s', 0)}s")
    lines.append("")

    # 2. QC
    lines.append("## 2. 数据质量")
    lines.append("")
    lines.append(f"- 存储行数: {coverage.get('rows', 0)} | 覆盖股票数: {coverage.get('codes', 0)}/{coverage.get('universe_size', 0)}")
    lines.append(f"- 覆盖率: {coverage.get('coverage_codes', 0):.1%} | 最新交易日: {coverage.get('last_date')}")
    lines.append(f"- 缺失股票数: {coverage.get('missing_count', 0)}")
    if coverage.get("missing_count", 0) > 10:
        lines.append("- ⚠️ 覆盖率低于预期，检查数据源")
    lines.append("")

    # 3. Mining
    lines.append("## 3. 因子挖掘")
    lines.append("")
    if mining.get("status") == "skipped":
        lines.append(f"- 跳过: {mining.get('reason')}")
    else:
        lines.append(
            f"- 评估 {mining.get('evaluated', 0)} 个候选因子 → 通过门槛 {mining.get('gated', 0)} 个 → "
            f"新注册 {mining.get('new_registered', 0)} 个（重复剔除 {mining.get('duplicates_rejected', 0)}）"
        )
        lines.append(f"- 评估窗口: {mining.get('panel_rows', 0)} 行 / {mining.get('panel_codes', 0)} 只股票")
        lines.append("")
        lines.append("| 因子 | IC | ICIR | 换手 | 状态 | 已注册 |")
        lines.append("|------|-----|------|------|------|--------|")
        for r in mining.get("results", []):
            lines.append(
                f"| {r['name']} | {r['ic']:+.4f} | {r['icir']:.2f} | {r['turnover']:.0%} | "
                f"{r['status']} | {'是' if r['already_registered'] else '否'} |"
            )
        lines.append("")
        if mining.get("new_factors"):
            lines.append("### 今日新注册因子")
            lines.append("")
            for r in mining["new_factors"]:
                lines.append(
                    f"- **{r['name']}**: IC={r['ic']:+.4f}, ICIR={r['icir']:.2f}, "
                    f"max_corr={r['corr_max']:.2f} ({r.get('corr_with', '-')})"
                )
        else:
            lines.append("今日无新因子通过门槛（继续积累数据，或放宽/调整候选集）。")
        lines.append("")

    # 4. Next steps
    lines.append("## 4. 下一步")
    lines.append("")
    lines.append("- 数据持续累积后，因子评估窗口自动扩大，IC/ICIR 估计更稳定")
    lines.append("- 通过门槛因子进入 factor_registry，供 M3 多策略组合使用")
    lines.append("- 接入 ClickHouse/SmartData 后切换全A股票池与分钟级数据")
    lines.append("")
    return "\n".join(lines)
