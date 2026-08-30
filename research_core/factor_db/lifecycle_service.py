"""生命周期面板数据服务。

聚合 runtime/lifecycle/ 下的三类产物，供面板展示因子从出生到死亡的全流程：

- ``g2_skeleton_report.json``  九道闸门逐因子逐闸门证据 + 死因
- ``evidence.jsonl``            证据链账本（状态跃迁记录）
- ``oos_access.json``           OOS 封存访问计数

输出契约（全部只读，不落任何写操作）：
- overview(): 状态计数 / 跃迁表 / 闸门漏斗 / 总量
- factor_rows(): 因子总表（状态、死因、OOS 额度、闸门摘要）
- factor_detail(): 单因子时间线 + 九道闸门完整证据
- evidence_feed(): 证据链事件流（最近优先）

正式流程（非骨架）的因子数据落在 lifecycle/evidence.jsonl，
骨架跑批落在 lifecycle/skeleton/，本服务合并两者。
"""

from __future__ import annotations

import json
from typing import Any

from common.paths import runtime_path

from research_core.factor_db.lifecycle import (
    G2_GATE_ORDER,
    LEGAL_TRANSITIONS,
    LIFECYCLE_STATES,
    MAX_OOS_ACCESS,
)

LIFECYCLE_DIR = runtime_path("lifecycle")
SKELETON_DIR = LIFECYCLE_DIR / "skeleton"
REPORT_PATH = LIFECYCLE_DIR / "g2_skeleton_report.json"
MONITOR_REPORT_PATH = LIFECYCLE_DIR / "monitor_report.json"

# 状态 → 展示配置（颜色对齐 trust.py 的分级色系）
STATE_VIEW: dict[str, dict[str, str]] = {
    "0_conceived": {"label": "设想", "color": "#a78bfa", "desc": "假设已登记（含 source_class）"},
    "1_implemented": {"label": "出生", "color": "#60a5fa", "desc": "代码可算、mock 通过"},
    "2_validated": {"label": "成年", "color": "#10b981", "desc": "九道验真全过"},
    "3_strategy_candidate": {"label": "准上岗", "color": "#34d399", "desc": "组合验证+仿真+容量"},
    "4_live_ready": {"label": "待上岗", "color": "#fbbf24", "desc": "人工批准通过"},
    "5_suspended": {"label": "暂停", "color": "#f59e0b", "desc": "衰减/证书到期/数据中断"},
    "6_published": {"label": "上架", "color": "#22c55e", "desc": "客户可见可订阅"},
    "7_deprecated": {"label": "降级", "color": "#fb923c", "desc": "有更优替代，迁移期"},
    "8_retired": {"label": "退休", "color": "#94a3b8", "desc": "摘牌，证据链保留"},
    "9_rejected": {"label": "死亡", "color": "#ef4444", "desc": "闸门淘汰，死因回注"},
}

GATE_VIEW: dict[str, dict[str, str]] = {
    "g4_data_quality": {"label": "4 数据质量", "desc": "缺失率<5%、覆盖≥90%、无前视"},
    "g5_executability": {"label": "5 可执行性", "desc": "涨跌停/停牌/ST/流动性过滤，衰减≤50%"},
    "g6_ic_stability": {"label": "6 IC稳定性", "desc": "ICIR>0.3 + bootstrap CI 不含 0"},
    "g7_multiple_testing": {"label": "7 多重检验", "desc": "BH-FDR 校正后 p≤0.05"},
    "g8_oos_retention": {"label": "8 OOS留存", "desc": "封存 holdout 留存≥70%（上限3次）"},
    "g9_cost_resilience": {"label": "9 成本韧性", "desc": "breakeven ≥ 2× 实际成本"},
    "g10_style_neutrality": {"label": "10 风格中性", "desc": "市值/行业/动量正交化后残差 IC"},
    "g11_market_segments": {"label": "11 市场分段", "desc": "≥3 年方向一致，最差年≥30%"},
    "g12_redundancy": {"label": "12 冗余去重", "desc": "相关性<0.7 + 增量 IC≥70%"},
}


class LifecycleDataError(RuntimeError):
    """生命周期产物缺失或损坏（先跑 g2_skeleton_run 生成）。"""


def _read_json(path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LifecycleDataError(f"{path.name} 损坏: {exc}") from exc


def _read_ledger(path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _current_state(factor_id: str, evidence: list[dict[str, Any]]) -> str | None:
    state = None
    for row in evidence:
        if row.get("factor_id") == factor_id:
            state = row["transition"].split("->")[1]
    return state


def factor_rows() -> list[dict[str, Any]]:
    """因子总表：合并骨架报告 + 证据链，推导当前状态。"""
    report = _read_json(REPORT_PATH)
    if report is None:
        raise LifecycleDataError(
            "runtime/lifecycle/g2_skeleton_report.json 不存在——"
            "先运行 python -X utf8 -m research_core.factor_db.g2_skeleton_run"
        )
    evidence = _read_ledger(SKELETON_DIR / "evidence.jsonl") + _read_ledger(
        LIFECYCLE_DIR / "evidence.jsonl"
    )
    oos = _read_json(SKELETON_DIR / "oos_access.json") or {}
    oos.update(_read_json(LIFECYCLE_DIR / "oos_access.json") or {})

    rows = []
    for rep in report.get("reports", []):
        fid = rep["factor"]
        state = _current_state(f"MOCK:{fid}", evidence)
        if state is None:
            # 无跃迁记录：按闸门结果推导（骨架口径）
            state = "2_validated" if rep.get("passed_all") else "9_rejected"
        oos_used = oos.get(f"MOCK:{fid}", 0)
        rows.append(
            {
                "factor_id": fid,
                "state": state,
                "state_label": STATE_VIEW.get(state, {}).get("label", state),
                "passed_all": rep.get("passed_all"),
                "first_failure": rep.get("first_failure"),
                "executed_order": rep.get("executed_order", []),
                "oos_access_used": oos_used,
                "oos_access_remaining": max(0, MAX_OOS_ACCESS - oos_used),
                "n_gates_passed": sum(1 for g in rep.get("gates", []) if g.get("passed")),
                "n_gates_run": len(rep.get("gates", [])),
            }
        )
    rows.sort(key=lambda r: (r["passed_all"] is not True, r["factor_id"]))
    return rows


def overview() -> dict[str, Any]:
    rows = factor_rows()
    counts = {s: 0 for s in LIFECYCLE_STATES}
    for r in rows:
        counts[r["state"]] = counts.get(r["state"], 0) + 1

    report = _read_json(REPORT_PATH) or {}
    funnel = []
    by_gate = report.get("failures_by_gate", {})
    for g in G2_GATE_ORDER:
        funnel.append(
            {
                "gate": g,
                "label": GATE_VIEW[g]["label"],
                "desc": GATE_VIEW[g]["desc"],
                "deaths": by_gate.get(g, 0),
            }
        )

    return {
        "total": len(rows),
        "validated": sum(1 for r in rows if r["state"] == "2_validated"),
        "rejected": sum(1 for r in rows if r["state"] == "9_rejected"),
        "state_counts": counts,
        "state_view": STATE_VIEW,
        "gate_funnel": funnel,
        "transitions": [dict(t) for t in LEGAL_TRANSITIONS],
        "prereg_split": report.get("prereg_split"),
        "max_oos_access": MAX_OOS_ACCESS,
    }


def factor_detail(factor_id: str) -> dict[str, Any]:
    """单因子：九道闸门完整证据 + 证据链时间线。"""
    report = _read_json(REPORT_PATH)
    if report is None:
        raise LifecycleDataError("先运行 g2_skeleton_run 生成报告")
    rep = next((r for r in report.get("reports", []) if r["factor"] == factor_id), None)
    if rep is None:
        raise LifecycleDataError(f"因子不在报告中: {factor_id}")

    evidence = _read_ledger(SKELETON_DIR / "evidence.jsonl") + _read_ledger(
        LIFECYCLE_DIR / "evidence.jsonl"
    )
    timeline = [e for e in evidence if e.get("factor_id") == f"MOCK:{factor_id}"]
    rows = factor_rows()
    row = next(r for r in rows if r["factor_id"] == factor_id)

    return {
        **row,
        "gates": [
            {
                "gate": g["gate"],
                "label": GATE_VIEW.get(g["gate"], {}).get("label", g["gate"]),
                "desc": GATE_VIEW.get(g["gate"], {}).get("desc", ""),
                "passed": g["passed"],
                "evidence": g.get("evidence", {}),
                "reason": g.get("reason", ""),
            }
            for g in rep.get("gates", [])
        ],
        "timeline": timeline,
    }


def monitor_report() -> dict[str, Any] | None:
    """衰减监控报告（先跑 lifecycle_monitor 生成；缺失返回 None）。"""
    report = _read_json(MONITOR_REPORT_PATH)
    if report is None:
        return None
    # 补充证书账本快照（到期倒计时，面板 SLA 区块渲染用）
    certs_path = LIFECYCLE_DIR / "certificates.json"
    certs = _read_json(certs_path) or {}
    report["certificates"] = {
        fid: {
            "issued_at": c.get("issued_at"),
            "valid_until": c.get("valid_until"),
            "owner": c.get("owner"),
        }
        for fid, c in certs.items()
    }
    return report


def sla_notifications() -> list[dict[str, Any]]:
    """SLA 通知事件流（监控报告的通知区，最近优先）。"""
    report = monitor_report()
    if report is None:
        return []
    notifications = list(report.get("notifications", []))
    notifications.sort(key=lambda n: n.get("generated_at", ""), reverse=True)
    return notifications


def evidence_feed(limit: int = 50) -> list[dict[str, Any]]:
    """证据链事件流（最近优先，跨骨架/正式两个账本）。"""
    feed = _read_ledger(SKELETON_DIR / "evidence.jsonl") + _read_ledger(
        LIFECYCLE_DIR / "evidence.jsonl"
    )
    feed.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
    return feed[:limit]
