"""G2 九道闸门骨架验证 CLI（mock 数据端到端跑通）。

流程（FACTOR_LIFECYCLE.md v2.0 G2 阶段）：
1. 构造 QAPI33 mock 面板（30 股 × 96 月，含 5 个预埋判别因子）
2. 逐因子按 4→5→…→12 固定顺序跑九道闸门
3. 闸门7 多重检验用本轮全体 33+5 个因子的 p 值（BH-FDR）
4. 闸门8 OOS 开封经 OOSAccessLedger 计数（每因子 1 次）
5. 通过者经 EvidenceLedger 写入 1_implemented->2_validated 证据链
6. 产出 runtime/lifecycle/g2_skeleton_report.json

预埋因子预期（验证闸门判别力，而非放水）：
- planted_good      → 全过（唯一 validated）
- planted_decay     → 挂闸门8（OOS 留存 <70%）
- planted_regime    → 挂闸门11（只牛市有 alpha）或闸门8
- planted_turnover  → 挂闸门9（breakeven 不足）或闸门6
- planted_crowded   → 挂闸门12（与 good 相关 >0.7）
- 33 个 QAPI33 mock 纯噪声因子 → 挂闸门6/7（ICIR 或 FDR）

用法：
    python -X utf8 -m research_core.factor_db.g2_skeleton_run
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from common.paths import runtime_path

from research_core.factor_db.g2_gates import run_g2
from research_core.factor_db.g2_mock_data import PREREG_SPLIT, build_long_panel
from research_core.factor_db.lifecycle import (
    EvidenceLedger,
    OOSAccessLedger,
)

REPORT_PATH = runtime_path("lifecycle", "g2_skeleton_report.json")
# 骨架跑批用独立目录，保证可复现（正式流程用 lifecycle/evidence.jsonl + oos_access.json，跨运行累计）
SKELETON_DIR = runtime_path("lifecycle", "skeleton")

PLANTED = ("planted_good", "planted_decay", "planted_regime", "planted_turnover", "planted_crowded")


def main() -> int:
    wide, names = build_long_panel()
    print(f"[mock] panel {wide.shape}, factors {len(names)}（含 5 个预埋判别因子）")

    # 第 1 遍：先算全体因子 IS 段 IC p 值（闸门7 多重检验的 N）
    from research_core.factor_db.g2_gates import _ic_pvalue

    is_wide = wide[wide["date"] < PREREG_SPLIT]
    pvals = {name: _ic_pvalue(is_wide, name) for name in names}

    # 第 2 遍：逐因子跑九道闸门（固定顺序逐道短路）
    ledger = EvidenceLedger(SKELETON_DIR / "evidence.jsonl")
    oos = OOSAccessLedger(SKELETON_DIR / "oos_access.json")
    reports = []
    library_cols: list[str] = []  # 通过者依次入库，后来者做增量检验

    for name in names:
        report = run_g2(
            wide,
            name,
            prereg_split=PREREG_SPLIT,
            library_cols=library_cols,
            all_factor_pvals=pvals,
        )
        reports.append(report)
        status = "PASS" if report.passed_all else f"FAIL@{report.first_failure}"
        print(f"  {name:24s} {status}")

        if report.passed_all:
            # OOS 计数（闸门8 开封 1 次）+ 证据链入账
            try:
                remaining = oos.access(f"MOCK:{name}")
            except Exception:
                continue
            library_cols.append(name)
            ledger.append(
                {
                    "factor_id": f"MOCK:{name}",
                    "transition": "1_implemented->2_validated",
                    "gate": "G2-4..12",
                    "evidence": {
                        g.gate: g.evidence for g in report.gates
                    },
                    "approved_by": "auto:agent",
                    "oos_access_remaining": remaining,
                }
            )

    passed = [r for r in reports if r.passed_all]
    failures: dict[str, int] = {}
    for r in reports:
        if r.first_failure:
            failures[r.first_failure] = failures.get(r.first_failure, 0) + 1

    summary = {
        "total": len(reports),
        "passed": len(passed),
        "passed_factors": [r.factor_col for r in passed],
        "failures_by_gate": failures,
        "prereg_split": PREREG_SPLIT,
        "oos_access_counts": {k: v for k, v in json.loads(oos.path.read_text(encoding="utf-8")).items()} if oos.path.exists() else {},
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(
            {**summary, "reports": [r.to_dict() for r in reports]},
            ensure_ascii=False,
            indent=2,
            default=lambda o: bool(o) if isinstance(o, (np.bool_,)) else float(o),
        ),
        encoding="utf-8",
    )

    print("\n===== G2 骨架验证摘要 =====")
    print(f"总计 {summary['total']} 个因子：{summary['passed']} 个过九道（validated）")
    for gate, n in sorted(failures.items()):
        print(f"  {gate}: 死亡 {n} 个")
    print(f"\n报告: {REPORT_PATH}")
    print(f"证据链: {ledger.path}（{len(ledger.entries())} 条）")

    # 判别力自检（骨架验证的核心断言）
    ok = True
    if "planted_good" not in summary["passed_factors"]:
        print("!! 判别力警告：planted_good 未通过全九道")
        ok = False
    for bad, expect_gate in (
        ("planted_decay", "g8_oos_retention"),
        ("planted_regime", "g11_market_segments"),
        ("planted_crowded", "g12_redundancy"),
    ):
        r = next(r for r in reports if r.factor_col == bad)
        if r.passed_all or r.first_failure != expect_gate:
            print(f"!! 判别力警告：{bad} 未按预期死在 {expect_gate}（实际 {r.first_failure}）")
            ok = False
    print(f"\n判别力自检：{'通过' if ok else '未通过'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
