#!/usr/bin/env python3
"""
Generate a detailed PR comment from validation results.

Takes unit test output, validation results, and changed factor info,
produces a structured markdown comment for the PR.
"""
from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _read_text(path: str | Path) -> str:
    target = Path(path)
    for encoding in ("utf-8", "utf-16", "utf-16-le", "utf-16-be", "gbk"):
        try:
            return target.read_text(encoding=encoding)
        except Exception:
            continue
    return target.read_text()


def _fmt_float(value: Any, precision: int = 6) -> str:
    """Format float for display, handle NaN/None."""
    if value is None:
        return "—"
    try:
        v = float(value)
        if math.isnan(v):
            return "—"
        return f"{v:.{precision}f}"
    except (TypeError, ValueError):
        return "—"


def _status_emoji(status: str) -> str:
    """Map status to emoji."""
    mapping = {
        "passed": "✅",
        "partial": "⚠️",
        "failed": "❌",
        "pending": "⏳",
        "pending_external_truth": "⏳",
        "not_compared": "⬜",
        "mismatch": "🔴",
        "exact_match": "✅",
    }
    return mapping.get(status, "❓")


def parse_unit_test_log(log_path: str) -> dict[str, Any]:
    """Parse pytest output to extract pass/fail summary."""
    try:
        text = _read_text(log_path)
    except Exception:
        return {"summary": "No unit test log found"}

    # Parse pytest summary line
    summary_matches = re.findall(r'=+ (.*?) =+', text)
    summary = summary_matches[-1] if summary_matches else "Could not parse summary"

    # Count passes and failures
    passed = len(re.findall(r' PASSED ', text))
    failed = len(re.findall(r' FAILED ', text))
    errors = len(re.findall(r' ERROR ', text))
    if passed == 0 and failed == 0 and errors == 0:
        summary_lower = summary.lower()
        passed_match = re.search(r'(\d+)\s+passed', summary_lower)
        failed_match = re.search(r'(\d+)\s+failed', summary_lower)
        error_match = re.search(r'(\d+)\s+error', summary_lower)
        passed = int(passed_match.group(1)) if passed_match else 0
        failed = int(failed_match.group(1)) if failed_match else 0
        errors = int(error_match.group(1)) if error_match else 0

    return {
        "summary": summary,
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "raw": text[-3000:],  # Last 3000 chars for detail
    }


def generate_comment(
    unit_test: dict,
    submission_test: dict,
    validation: dict,
    changes: dict,
) -> str:
    """Generate the PR comment markdown."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        "## 🤖 因子自动验证报告",
        "",
        f"*生成时间: {now}*",
        "",
        "---",
        "",
    ]

    # === Summary Bar ===
    test_total = unit_test.get("passed", 0) + unit_test.get("failed", 0) + unit_test.get("errors", 0)
    test_status = "✅ 全部通过" if unit_test.get("failed", 0) == 0 and unit_test.get("errors", 0) == 0 else "❌ 存在失败"
    submission_test_total = submission_test.get("passed", 0) + submission_test.get("failed", 0) + submission_test.get("errors", 0)
    submission_test_status = "✅ 全部通过" if submission_test.get("failed", 0) == 0 and submission_test.get("errors", 0) == 0 else "❌ 存在失败"

    lines.extend([
        "### 📊 概览",
        "",
        f"| 检查项 | 结果 |",
        f"|---|---|",
        f"| 单元测试 (Layer 1: 公式正确性) | {test_status} ({test_total} tests) |",
        f"| 提交测试 (Layer 1: submissions) | {submission_test_status} ({submission_test_total} tests) |",
    ])

    # Alpha101 validation
    alpha = validation.get("alpha101", {})
    if alpha and "note" not in alpha:
        alpha_status = alpha.get("status", "unknown")
        n_factors = len(alpha.get("requested_factors", []))
        lines.append(f"| Alpha101 验证 (Layer 2+3) | {_status_emoji(alpha_status)} {alpha_status} ({n_factors} factors) |")

    # Submission validation
    subs = validation.get("submissions", {})
    if subs:
        sub_failed = sum(1 for s in subs.values() if s.get("status") == "failed")
        sub_passed = sum(1 for s in subs.values() if s.get("status") == "passed")
        sub_status = "✅ 全部通过" if sub_failed == 0 else f"❌ {sub_failed} failed, {sub_passed} passed"
        lines.append(f"| 提交因子验证 | {sub_status} |")

    lines.append("")
    lines.append("---")

    # === Unit Test Details ===
    if unit_test.get("failed", 0) > 0 or unit_test.get("errors", 0) > 0:
        lines.extend([
            "",
            "### 🔴 单元测试失败详情",
            "",
            "```text",
            unit_test.get("raw", "No details available")[:2000],
            "```",
        ])

    if submission_test.get("failed", 0) > 0 or submission_test.get("errors", 0) > 0:
        lines.extend([
            "",
            "### 🔴 提交测试失败详情",
            "",
            "```text",
            submission_test.get("raw", "No details available")[:2000],
            "```",
        ])

    # === Alpha101 Factor Results ===
    if alpha and "requested_factors" in alpha and alpha.get("requested_factors"):
        lines.extend([
            "",
            "### 📈 Alpha101 因子验证结果",
            "",
        ])

        # Read proof report if available
        artifacts = alpha.get("artifacts", {})
        report_path = artifacts.get("research_report_markdown", "")

        if report_path and Path(report_path).exists():
            # Embed the generated report
            report_content = _read_text(report_path)
            lines.append(report_content)
        else:
            # Build summary from eval data
            dataset = alpha.get("dataset", {})
            lines.append(f"*数据集: {dataset.get('n_dates', '?')} dates × {dataset.get('n_codes', '?')} codes*")
            lines.append("")

        # Per-factor proof details
        proofs = artifacts.get("proofs", {})
        if proofs:
            lines.extend([
                "#### 逐因子验证详情",
                "",
            ])
            for fname, proof_path in sorted(proofs.items()):
                if Path(proof_path).exists():
                    proof = json.loads(_read_text(proof_path))
                    status = proof.get("status", "unknown")
                    checks = proof.get("checks", [])
                    diag = proof.get("diagnostics", {})

                    lines.append(f"**{fname}** — {_status_emoji(status)} {status}")
                    lines.append("")

                    # Checks table
                    for check in checks:
                        c_status = check["status"]
                        lines.append(f"- {_status_emoji(c_status)} **{check['name']}**: {check['description']}")

                    # Metrics
                    if diag:
                        lines.append("")
                        lines.append(f"  IC Mean: `{_fmt_float(diag.get('rank_ic_mean'))}` | "
                                     f"ICIR: `{_fmt_float(diag.get('rank_ic_ir'))}` | "
                                     f"Coverage: `{_fmt_float(diag.get('coverage_ratio'), 2)}`")

                    lines.append("")

    # === Submission Results ===
    if subs:
        lines.extend([
            "",
            "### 📦 提交因子验证结果",
            "",
        ])

        for sub_dir, result in sorted(subs.items()):
            name = result.get("factor_name", sub_dir)
            status = result.get("status", "failed")
            checks = result.get("checks", [])
            ev = result.get("evaluation", {})

            lines.append(f"**{name}** ({sub_dir}) — {_status_emoji(status)} {status}")
            lines.append("")

            if result.get("error"):
                lines.append(f"- ❌ **error**: {result['error']}")

            for check in checks:
                c_status = check["status"]
                lines.append(f"- {_status_emoji(c_status)} **{check['name']}**: {check['description']}")

            if ev:
                lines.append("")
                lines.append(f"  IC Mean: `{_fmt_float(ev.get('rank_ic_mean'))}` | "
                             f"ICIR: `{_fmt_float(ev.get('rank_ic_ir'))}` | "
                             f"Coverage: `{_fmt_float(ev.get('coverage_ratio'), 2)}`")
            lines.append("")

    # === Footer ===
    lines.extend([
        "---",
        "",
        "### 🔍 验证说明",
        "",
        "本报告基于三层验证框架生成：",
        "",
        "| 层级 | 检查内容 | 方法 |",
        "|---|---|---|",
        "| **Layer 1** | 公式正确性 | 单元测试 + 合成数据手算验证 |",
        "| **Layer 2** | 数据一致性 | 字段映射校验 + 样本点核验 |",
        "| **Layer 3** | 外部真值对照 | 与米筐/聚宽等外部数据对比 |",
        "",
        "**有效性指标阈值**:",
        "- Rank IC 均值 > 0.02 视为有效预测力",
        "- |ICIR| > 0.3 视为预测稳定",
        "- Coverage > 50% 视为覆盖充分",
        "",
        "需要人工复核的场景：",
        "- ICIR < 0.3 但 IC 均值 > 0.02 → 预测不稳定，需扩大时间窗口验证",
        "- Coverage < 50% → 因子存在大量空值，检查计算逻辑和边界处理",
        "- Layer 3 标记为 `pending_external_truth` → 尚未挂接外部真值",
    ])

    return "\n".join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--unit-test-log', default='/tmp/unit_test_output.txt')
    parser.add_argument('--submission-test-log', default='/tmp/submission_test_output.txt')
    parser.add_argument('--validation-dir', default='/tmp/validation_output')
    parser.add_argument('--changed-json', default='/tmp/changed_factors.json')
    parser.add_argument('--output', default='/tmp/pr_comment.md')
    args = parser.parse_args()

    unit_test = parse_unit_test_log(args.unit_test_log)
    submission_test = parse_unit_test_log(args.submission_test_log)

    validation = {}
    results_path = Path(args.validation_dir) / "results.json"
    if results_path.exists():
        validation = json.loads(_read_text(results_path))

    changes = {}
    changes_path = Path(args.changed_json)
    if changes_path.exists():
        changes = json.loads(_read_text(changes_path))

    comment = generate_comment(unit_test, submission_test, validation, changes)

    Path(args.output).write_text(comment, encoding="utf-8")
    print(f"PR comment written to {args.output}")
    print(f"Comment length: {len(comment)} chars")


if __name__ == '__main__':
    main()
