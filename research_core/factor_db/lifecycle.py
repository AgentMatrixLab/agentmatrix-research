"""因子生命周期内核（FACTOR_LIFECYCLE.md v2.0 的代码承载）。

宪法条款的代码化，全部不依赖真实数据，可在闸门统计实现之前先行落地：

1. **状态机**：10 个状态 + 13 条合法跃迁（唯一权威表）。任何表外跃迁
   :class:`IllegalTransition` 直接拒绝——对应宪法"CI 直接拒绝"。
2. **闸门1 假设登记**：四项齐备（假设陈述 / 出处 / 预期方向 / 经济学逻辑）
   + ``source_class``（novel / replication）+ 方向锁定（事后翻转符号计为
   一次未申报试验）。
3. **证据链**：append-only JSONL 账本。无证据记录的状态变更视为非法。
4. **OOS 访问计数**：同一 factor_id 访问封存 holdout 上限 3 次，第 4 次
   自动 ``rejected``。
5. **证书 12 必填字段**：缺任一字段不得签发（闸门16）。
6. **闸门顺序**：G2 九道按 4→5→…→12 固定顺序逐道短路（修正 C）。

运行时产物（runtime/lifecycle/，禁止提交 git）：
- ``evidence.jsonl``  证据链账本
- ``oos_access.json`` OOS 访问计数器

后续接线：G2 统计闸门（miner.py）跑出数值后调用 :meth:`EvidenceLedger.append`
写入证据；面板 / Supabase 只读本模块产出的状态。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from common.paths import runtime_path

EVIDENCE_LEDGER_PATH = runtime_path("lifecycle", "evidence.jsonl")
OOS_ACCESS_PATH = runtime_path("lifecycle", "oos_access.json")

# ---------------------------------------------------------------------------
# 1. 状态机（跃迁全表 · 唯一权威）
# ---------------------------------------------------------------------------

LIFECYCLE_STATES: dict[str, str] = {
    "0_conceived": "设想（假设已登记，含 source_class）",
    "1_implemented": "出生（代码可算、mock 通过）",
    "2_validated": "成年（九道验真通过）",
    "3_strategy_candidate": "准上岗（组合验证 + 外部仿真 + 容量）",
    "4_live_ready": "通过人工批准",
    "5_suspended": "暂停（衰减 / 证书到期 / 数据中断）",
    "6_published": "上架（客户可见可订阅）",
    "7_deprecated": "降级（有更优替代，迁移期中）",
    "8_retired": "退休（摘牌，证据链保留）",
    "9_rejected": "死亡（闸门淘汰，死因回注，终态）",
}

# 宪法 §0 跃迁全表：13 条合法跃迁。代码以此表为准，图表仅供参考。
LEGAL_TRANSITIONS: tuple[dict[str, str], ...] = (
    {"from": "inspiration_pool", "to": "0_conceived", "gate": "G0-1", "approver": "auto"},
    {"from": "inspiration_pool", "to": "9_rejected", "gate": "G0-1-fail", "approver": "auto"},
    {"from": "0_conceived", "to": "1_implemented", "gate": "G1-2,3", "approver": "auto"},
    {"from": "1_implemented", "to": "2_validated", "gate": "G2-4..12", "approver": "auto"},
    {"from": "2_validated", "to": "3_strategy_candidate", "gate": "G3-13,14,14b", "approver": "auto"},
    {"from": "3_strategy_candidate", "to": "4_live_ready", "gate": "G4-15", "approver": "human"},
    {"from": "4_live_ready", "to": "6_published", "gate": "G5-16", "approver": "auto"},
    {"from": "6_published", "to": "5_suspended", "gate": "decay/expiry/outage", "approver": "auto"},
    {"from": "5_suspended", "to": "6_published", "gate": "revalidate", "approver": "human"},
    {"from": "5_suspended", "to": "8_retired", "gate": "revalidate-fail/30d", "approver": "auto"},
    {"from": "6_published", "to": "7_deprecated", "gate": "superseded", "approver": "human"},
    {"from": "7_deprecated", "to": "8_retired", "gate": "migration-90d", "approver": "auto"},
    # 任意状态 → rejected（宪法允许即时死亡，本表以 from="*" 表达）
    {"from": "*", "to": "9_rejected", "gate": "any-gate-fail", "approver": "auto"},
)


class LifecycleError(Exception):
    """生命周期宪法违规的基类。"""


class IllegalTransition(LifecycleError):
    """跃迁不在 13 条合法跃迁表内。"""


class HypothesisRejected(LifecycleError):
    """闸门1 四项不齐备，不入队。"""


class OOSAccessLimitExceeded(LifecycleError):
    """同一 factor_id 第 4 次访问封存 holdout，自动 rejected。"""


class CertificateIncomplete(LifecycleError):
    """证书 12 必填字段缺失，不得上架。"""


def validate_transition(from_state: str, to_state: str) -> dict[str, str]:
    """校验跃迁是否在合法表内，返回该跃迁的登记行；非法则抛
    :class:`IllegalTransition`。"""
    for row in LEGAL_TRANSITIONS:
        if row["from"] == from_state and row["to"] == to_state:
            return row
        if row["from"] == "*" and row["to"] == to_state and from_state not in (
            "inspiration_pool",
        ):
            return {**row, "from": from_state}
    raise IllegalTransition(
        f"非法跃迁 {from_state} -> {to_state}：不在 13 条合法跃迁表内（FACTOR_LIFECYCLE.md v2.0 §0）"
    )


def legal_targets(state: str) -> list[str]:
    """某状态的所有合法去向（供 UI / CI 提示）。"""
    targets = [r["to"] for r in LEGAL_TRANSITIONS if r["from"] == state]
    targets += [r["to"] for r in LEGAL_TRANSITIONS if r["from"] == "*"]
    return sorted(set(targets))


# ---------------------------------------------------------------------------
# 2. 闸门1 · 假设登记（G0）
# ---------------------------------------------------------------------------

SOURCE_CLASSES = ("novel", "replication")


@dataclass
class Hypothesis:
    """``factor_hypothesis`` 登记记录（闸门1 四项 + source_class + 方向锁定）。

    方向锁定：``expected_direction`` 入队即锁死。事后因 IC 为负翻转符号
    = 一次未申报的样本内试验，须计入闸门7 试验次数 N。
    """

    factor_id: str
    statement: str  # ① 假设陈述
    source_ref: str  # ② 出处（DOI / 研报页码 / prompt+模型版本+温度）
    expected_direction: int  # ③ 预期方向：+1 / -1，入队锁死
    econ_logic: str  # ④ 经济学逻辑一句话
    source_class: str = "novel"  # novel / replication
    prereg_split_date: str | None = None  # novel 类：预注册 IS/OOS 切分点
    created_at: str = field(default_factory=lambda: _now_iso())

    def validate(self) -> list[str]:
        """闸门1：返回缺失项清单；空清单 = 可入队。"""
        missing: list[str] = []
        if not self.statement.strip():
            missing.append("statement（假设陈述）")
        if not self.source_ref.strip():
            missing.append("source_ref（出处）")
        if self.expected_direction not in (1, -1):
            missing.append("expected_direction（预期方向，须为 +1/-1）")
        if not self.econ_logic.strip():
            missing.append("econ_logic（经济学逻辑）")
        if self.source_class not in SOURCE_CLASSES:
            missing.append(f"source_class（须为 {'/'.join(SOURCE_CLASSES)}）")
        if self.source_class == "novel" and not self.prereg_split_date:
            missing.append("prereg_split_date（novel 类必须在实现前锁定切分点）")
        return missing

    def direction_flipped(self, observed_sign: int) -> bool:
        """观察到的 IC 符号与锁定方向相反 = 未申报试验，计入 N。"""
        return observed_sign not in (0, self.expected_direction)


# ---------------------------------------------------------------------------
# 3. G2 闸门注册表（固定执行顺序 · 修正 C）
# ---------------------------------------------------------------------------

G2_GATE_ORDER: tuple[str, ...] = (
    "g4_data_quality",
    "g5_executability",
    "g6_ic_stability",
    "g7_multiple_testing",
    "g8_oos_retention",
    "g9_cost_resilience",
    "g10_style_neutrality",
    "g11_market_segments",
    "g12_redundancy",
)


def assert_gate_order(executed: list[str]) -> None:
    """闸门按 4→5→…→12 固定顺序逐道短路；乱序即违宪。"""
    expected = list(G2_GATE_ORDER)
    seen = [g for g in expected if g in executed]
    if seen != executed:
        raise LifecycleError(
            f"闸门执行顺序违规：{executed}，须按 {expected} 逐道短路（FACTOR_LIFECYCLE.md v2.0 修正 C）"
        )


# ---------------------------------------------------------------------------
# 4. 证据链账本（append-only）
# ---------------------------------------------------------------------------

REQUIRED_EVIDENCE_KEYS = ("factor_id", "transition", "gate", "evidence", "approved_by")


class EvidenceLedger:
    """append-only JSONL 证据账本。

    规则：**无证据记录的状态变更视为非法变更**。每个跃迁一条记录，
    任何人任何时候可复核"谁、用什么数据、什么代码、何时"。
    """

    def __init__(self, path: Path = EVIDENCE_LEDGER_PATH) -> None:
        self.path = path

    def append(self, record: dict[str, Any]) -> dict[str, Any]:
        for key in REQUIRED_EVIDENCE_KEYS:
            if key not in record:
                raise LifecycleError(f"证据记录缺必填键 {key}")
        validate_transition(*record["transition"].split("->"))
        record = {"timestamp": _now_iso(), **record}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record

    def entries(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
        return rows

    def current_state(self, factor_id: str) -> str | None:
        state: str | None = None
        for row in self.entries():
            if row.get("factor_id") == factor_id:
                state = row["transition"].split("->")[1]
        return state

    def has_evidence(self, factor_id: str, transition: str) -> bool:
        return any(
            row.get("factor_id") == factor_id and row.get("transition") == transition
            for row in self.entries()
        )


# ---------------------------------------------------------------------------
# 5. OOS 访问计数器（封存 holdout · 上限 3 次）
# ---------------------------------------------------------------------------

MAX_OOS_ACCESS = 3


class OOSAccessLedger:
    """同一 factor_id 访问封存 holdout 的计数器。

    第 1—3 次返回剩余额度；第 4 次抛 :class:`OOSAccessLimitExceeded`，
    调用方应将因子转入 ``9_rejected``。
    """

    def __init__(self, path: Path = OOS_ACCESS_PATH) -> None:
        self.path = path

    def _load(self) -> dict[str, int]:
        if self.path.exists():
            return json.loads(self.path.read_text(encoding="utf-8"))
        return {}

    def _save(self, data: dict[str, int]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def count(self, factor_id: str) -> int:
        return self._load().get(factor_id, 0)

    def access(self, factor_id: str) -> int:
        data = self._load()
        used = data.get(factor_id, 0)
        if used >= MAX_OOS_ACCESS:
            raise OOSAccessLimitExceeded(
                f"{factor_id} 已访问封存 holdout {used} 次（上限 {MAX_OOS_ACCESS}），"
                "自动转入 9_rejected（FACTOR_LIFECYCLE.md v2.0 闸门8）"
            )
        data[factor_id] = used + 1
        self._save(data)
        return MAX_OOS_ACCESS - data[factor_id]


# ---------------------------------------------------------------------------
# 6. 证书 12 必填字段（闸门16）
# ---------------------------------------------------------------------------

CERTIFICATE_REQUIRED_FIELDS: tuple[str, ...] = (
    "factor_identity",  # 1 factor_id / 名称 / 一句话经济学逻辑
    "gates_passed",  # 2 闸门 4—16 逐项打勾
    "rank_ic_icir",  # 3 月频 Rank IC / ICIR（含 bootstrap 95% CI）
    "oos_retention_split",  # 4 OOS 留存率 + IS/OOS 切分日期（预注册值）
    "trials_n_deflated_sharpe",  # 5 试验次数 N + Deflated Sharpe
    "capacity",  # 6 容量上限（alpha 衰减 ≤30% 的最大规模）
    "breakeven_cost_turnover",  # 7 breakeven cost + 年化双边换手
    "data_source_universe_window",  # 8 含 PIT 与 announcement date 声明
    "code_commit_runner",  # 9 可复现性锚点
    "verified_at_valid_until",  # 10 验证时间 + 有效期（6 个月）
    "owner",  # 11 负责人（署真名）
    "delisting_sla",  # 12 摘牌 SLA
)


def validate_certificate(certificate: dict[str, Any]) -> list[str]:
    """闸门16：返回缺失字段清单；空清单 = 可签发上架。"""
    return [f for f in CERTIFICATE_REQUIRED_FIELDS if not certificate.get(f)]


def issue_certificate(certificate: dict[str, Any]) -> dict[str, Any]:
    """签发证书；缺任一字段抛 :class:`CertificateIncomplete`，不得上架。"""
    missing = validate_certificate(certificate)
    if missing:
        raise CertificateIncomplete(f"证书缺 {len(missing)} 个必填字段：{missing}")
    return {"issued_at": _now_iso(), **certificate}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


__all__ = [
    "LIFECYCLE_STATES",
    "LEGAL_TRANSITIONS",
    "LifecycleError",
    "IllegalTransition",
    "HypothesisRejected",
    "OOSAccessLimitExceeded",
    "CertificateIncomplete",
    "validate_transition",
    "legal_targets",
    "Hypothesis",
    "SOURCE_CLASSES",
    "G2_GATE_ORDER",
    "assert_gate_order",
    "EvidenceLedger",
    "OOSAccessLedger",
    "MAX_OOS_ACCESS",
    "CERTIFICATE_REQUIRED_FIELDS",
    "validate_certificate",
    "issue_certificate",
]
