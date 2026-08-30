"""因子生命周期内核测试（FACTOR_LIFECYCLE.md v2.0 的宪法条款逐条验证）。

覆盖：13 条合法跃迁 / 表外跃迁拒绝 / 闸门1 四项齐备 / source_class 分层 /
方向锁定 / 闸门顺序 / 证据链 / OOS 访问上限 / 证书 12 字段。
"""

from __future__ import annotations

import json

import pytest

from research_core.factor_db import lifecycle as lc


# ---------------------------------------------------------------------------
# 状态机
# ---------------------------------------------------------------------------


class TestStateMachine:
    def test_thirteen_legal_transitions_present(self):
        # 12 条显式 + 1 条通配（任意状态 → rejected）
        assert len(lc.LEGAL_TRANSITIONS) == 13

    def test_happy_path_transitions_all_legal(self):
        path = [
            ("inspiration_pool", "0_conceived"),
            ("0_conceived", "1_implemented"),
            ("1_implemented", "2_validated"),
            ("2_validated", "3_strategy_candidate"),
            ("3_strategy_candidate", "4_live_ready"),
            ("4_live_ready", "6_published"),
        ]
        for src, dst in path:
            row = lc.validate_transition(src, dst)
            assert row["to"] == dst

    def test_any_state_can_reject(self):
        for state in ("2_validated", "6_published", "0_conceived"):
            lc.validate_transition(state, "9_rejected")

    def test_skip_level_is_illegal(self):
        # 跳级：implemented 直达 strategy_candidate
        with pytest.raises(lc.IllegalTransition):
            lc.validate_transition("1_implemented", "3_strategy_candidate")

    def test_backward_revival_is_illegal(self):
        # rejected 是终态，不得复活
        with pytest.raises(lc.IllegalTransition):
            lc.validate_transition("9_rejected", "2_validated")

    def test_human_gates_are_enumerated(self):
        # 人工点恰好 3 处：闸门15 批准 / suspended 重验 / deprecated 降级
        human_rows = [r for r in lc.LEGAL_TRANSITIONS if r["approver"] == "human"]
        assert len(human_rows) == 3
        row = lc.validate_transition("3_strategy_candidate", "4_live_ready")
        assert row["approver"] == "human"
        assert row["gate"] == "G4-15"


# ---------------------------------------------------------------------------
# 闸门1 假设登记
# ---------------------------------------------------------------------------


class TestHypothesis:
    def _full(self, **kwargs):
        base = dict(
            factor_id="TEST:factor_a",
            statement="高换手率预示短期反转",
            source_ref="WorldQuant 101 Alphas, alpha#6",
            expected_direction=-1,
            econ_logic="流动性提供者补偿，高换手=拥挤=回撤",
            source_class="novel",
            prereg_split_date="2024-06-30",
        )
        base.update(kwargs)
        return lc.Hypothesis(**base)

    def test_gate1_complete_passes(self):
        assert self._full().validate() == []

    def test_gate1_missing_econ_logic_rejected(self):
        missing = self._full(econ_logic="").validate()
        assert "econ_logic（经济学逻辑）" in missing

    def test_gate1_missing_source_rejected(self):
        assert "source_ref（出处）" in self._full(source_ref="").validate()

    def test_invalid_source_class_rejected(self):
        assert self._full(source_class="unknown").validate() != []

    def test_novel_requires_prereg_split(self):
        missing = self._full(source_class="novel", prereg_split_date=None).validate()
        assert "prereg_split_date（novel 类必须在实现前锁定切分点）" in missing
        # replication 类不要求预注册（OOS 基线为发表后）
        assert self._full(source_class="replication", prereg_split_date=None).validate() == []

    def test_direction_lock_detects_flip(self):
        hyp = self._full(expected_direction=1)
        assert hyp.direction_flipped(-1) is True  # 未申报试验，计入 N
        assert hyp.direction_flipped(1) is False
        assert hyp.direction_flipped(0) is False  # 无信号不算翻转


# ---------------------------------------------------------------------------
# 闸门顺序（修正 C）
# ---------------------------------------------------------------------------


class TestGateOrder:
    def test_full_ordered_run_ok(self):
        lc.assert_gate_order(list(lc.G2_GATE_ORDER))

    def test_short_circuit_ok(self):
        # 逐道短路：g4 失败即出局，不再跑后面
        lc.assert_gate_order(["g4_data_quality"])

    def test_out_of_order_rejected(self):
        with pytest.raises(lc.LifecycleError):
            lc.assert_gate_order(["g6_ic_stability", "g4_data_quality"])

    def test_unknown_gate_rejected(self):
        with pytest.raises(lc.LifecycleError):
            lc.assert_gate_order(["g4_data_quality", "g99_unknown"])


# ---------------------------------------------------------------------------
# 证据链 + OOS 计数器（用 tmp_path 隔离）
# ---------------------------------------------------------------------------


class TestEvidenceAndOOS:
    def test_append_and_replay(self, tmp_path):
        ledger = lc.EvidenceLedger(tmp_path / "evidence.jsonl")
        record = ledger.append(
            {
                "factor_id": "QAPI33:roe_ttm",
                "transition": "1_implemented->2_validated",
                "gate": "G2-4..12",
                "evidence": {"is_ic": 0.062, "oos_ic": 0.055},
                "approved_by": "auto:agent",
            }
        )
        assert record["timestamp"]
        assert ledger.current_state("QAPI33:roe_ttm") == "2_validated"
        assert ledger.has_evidence("QAPI33:roe_ttm", "1_implemented->2_validated")

    def test_append_requires_all_keys(self, tmp_path):
        ledger = lc.EvidenceLedger(tmp_path / "evidence.jsonl")
        with pytest.raises(lc.LifecycleError):
            ledger.append({"factor_id": "x", "transition": "0_conceived->1_implemented"})

    def test_append_rejects_illegal_transition(self, tmp_path):
        ledger = lc.EvidenceLedger(tmp_path / "evidence.jsonl")
        with pytest.raises(lc.IllegalTransition):
            ledger.append(
                {
                    "factor_id": "x",
                    "transition": "1_implemented->6_published",  # 跳级
                    "gate": "G2",
                    "evidence": {},
                    "approved_by": "auto:agent",
                }
            )

    def test_oos_access_limit_three(self, tmp_path):
        oos = lc.OOSAccessLedger(tmp_path / "oos_access.json")
        assert oos.access("f1") == 2  # 第 1 次，剩 2
        assert oos.access("f1") == 1  # 第 2 次，剩 1
        assert oos.access("f1") == 0  # 第 3 次，剩 0
        with pytest.raises(lc.OOSAccessLimitExceeded):  # 第 4 次 → rejected
            oos.access("f1")
        assert oos.count("f1") == 3

    def test_oos_counts_are_per_factor(self, tmp_path):
        oos = lc.OOSAccessLedger(tmp_path / "oos_access.json")
        oos.access("f1")
        assert oos.count("f2") == 0


# ---------------------------------------------------------------------------
# 证书 12 字段
# ---------------------------------------------------------------------------


class TestCertificate:
    def _full_cert(self, **overrides):
        cert = {name: "x" for name in lc.CERTIFICATE_REQUIRED_FIELDS}
        cert.update(overrides)
        return cert

    def test_twelve_fields_required(self):
        assert len(lc.CERTIFICATE_REQUIRED_FIELDS) == 12

    def test_complete_certificate_issues(self):
        issued = lc.issue_certificate(self._full_cert())
        assert issued["issued_at"]

    def test_missing_field_blocks_issue(self):
        cert = self._full_cert()
        del cert["trials_n_deflated_sharpe"]  # v2.0 新增：没有 N，IC 无意义
        with pytest.raises(lc.CertificateIncomplete):
            lc.issue_certificate(cert)

    def test_empty_field_counts_as_missing(self):
        cert = self._full_cert(capacity="")  # 容量上限缺失
        assert lc.validate_certificate(cert) == ["capacity"]
