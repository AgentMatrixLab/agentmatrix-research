"""衰减监控与摘牌自动化测试（FACTOR_LIFECYCLE.md v2.0 运营层量化触发逐条验证）。

覆盖：衰减预警（50%×连续2月）/ 5_suspended 四类触发 / 30 天重验期限 /
90 天迁移期满 / 证书 6 个月有效期与到期倒计时 / SLA 通知 /
run_monitor 自动跃迁写证据链。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from research_core.factor_db import lifecycle as lc
from research_core.factor_db import lifecycle_monitor as mon


NOW = datetime(2026, 8, 30, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# 纯判定函数
# ---------------------------------------------------------------------------


class TestDecayWarning:
    def test_two_consecutive_months_below_half_triggers(self):
        # 上架 IC 0.06，50% 阈值 0.03；最近两个月 0.028 / 0.025 连续低于
        r = mon.decay_warning(0.06, [0.055, 0.028, 0.025])
        assert r["warn"] is True
        assert r["months_below"] == 2
        assert r["threshold"] == pytest.approx(0.03)

    def test_single_bad_month_does_not_trigger(self):
        # 末位 = 最新月：只有中间月差，最新月回升 → 不触发
        r = mon.decay_warning(0.06, [0.055, 0.025, 0.045])
        assert r["warn"] is False
        assert r["months_below"] == 0
        # 最新月差一个月，前一月回升 → 单月不触发
        r2 = mon.decay_warning(0.06, [0.055, 0.045, 0.025])
        assert r2["warn"] is False
        assert r2["months_below"] == 1

    def test_healthy_factor_no_warning(self):
        r = mon.decay_warning(0.06, [0.062, 0.058, 0.060])
        assert r["warn"] is False


class TestSuspendReasons:
    def test_icir_below_floor(self):
        reasons = mon.suspend_reasons(
            metrics={"icir_12m": 0.08},
            cert_days_remaining=90,
            data_stale_days=1,
        )
        assert any("ICIR" in r for r in reasons)

    def test_cert_expired(self):
        reasons = mon.suspend_reasons(
            metrics={"icir_12m": 0.40},
            cert_days_remaining=-3,
            data_stale_days=1,
        )
        assert any("证书到期" in r for r in reasons)

    def test_data_outage_over_five_trading_days(self):
        reasons = mon.suspend_reasons(
            metrics={"icir_12m": 0.40},
            cert_days_remaining=90,
            data_stale_days=6,
        )
        assert any("数据源中断" in r for r in reasons)

    def test_watch_unrecovered(self):
        reasons = mon.suspend_reasons(
            metrics=None,
            cert_days_remaining=90,
            data_stale_days=0,
            in_watch_unrecovered=True,
        )
        assert any("观察期" in r for r in reasons)

    def test_healthy_factor_no_reasons(self):
        assert (
            mon.suspend_reasons(
                metrics={"icir_12m": 0.40},
                cert_days_remaining=90,
                data_stale_days=2,
            )
            == []
        )


class TestRetireReasons:
    def test_suspended_over_30_days(self):
        since = (NOW - timedelta(days=31)).strftime("%Y-%m-%d")
        reasons = mon.retire_reasons("5_suspended", since, NOW)
        assert any("未完成重验" in r for r in reasons)

    def test_suspended_within_deadline_ok(self):
        since = (NOW - timedelta(days=29)).strftime("%Y-%m-%d")
        assert mon.retire_reasons("5_suspended", since, NOW) == []

    def test_deprecated_migration_90d_elapsed(self):
        since = (NOW - timedelta(days=91)).strftime("%Y-%m-%d")
        reasons = mon.retire_reasons("7_deprecated", since, NOW)
        assert any("迁移期" in r for r in reasons)

    def test_deprecated_within_migration_ok(self):
        since = (NOW - timedelta(days=60)).strftime("%Y-%m-%d")
        assert mon.retire_reasons("7_deprecated", since, NOW) == []


# ---------------------------------------------------------------------------
# 证书账本（6 个月有效期）
# ---------------------------------------------------------------------------


def _full_cert(factor_id="QAPI33:roe_ttm", **overrides):
    cert = {name: "x" for name in lc.CERTIFICATE_REQUIRED_FIELDS}
    cert["factor_identity"] = factor_id
    cert.update(overrides)
    return cert


class TestCertificateLedger:
    def test_issue_sets_six_month_validity(self, tmp_path):
        certs = lc.CertificateLedger(tmp_path / "certificates.json")
        issued = certs.issue(_full_cert())
        # 不校验具体日历：只验证 valid_until 比 issued_at 晚约 6 个月（183±2 天）
        t0 = datetime.strptime(issued["issued_at"], "%Y-%m-%dT%H:%M:%SZ")
        t1 = datetime.strptime(issued["valid_until"], "%Y-%m-%dT%H:%M:%SZ")
        assert 181 <= (t1 - t0).days <= 184

    def test_days_remaining_positive_then_expires(self, tmp_path):
        certs = lc.CertificateLedger(tmp_path / "certificates.json")
        cert = _full_cert(valid_until="1970-01-01T00:00:00Z")
        certs.issue(cert)
        assert certs.days_remaining("QAPI33:roe_ttm") < 0  # 早已过期

    def test_add_months_handles_month_ends(self):
        assert lc._add_months("2026-08-31T00:00:00Z", 6) == "2027-02-28T00:00:00Z"
        assert lc._add_months("2026-02-28T00:00:00Z", 6) == "2026-08-28T00:00:00Z"


# ---------------------------------------------------------------------------
# run_monitor 端到端（tmp_path 隔离账本）
# ---------------------------------------------------------------------------


def _publish(ledger, fid, timestamp="2026-01-01T00:00:00Z"):
    """把一个因子沿合法路径推到 published（手工铺证据链时间戳）。"""
    chain = [
        ("inspiration_pool", "0_conceived", "G0-1"),
        ("0_conceived", "1_implemented", "G1-2,3"),
        ("1_implemented", "2_validated", "G2-4..12"),
        ("2_validated", "3_strategy_candidate", "G3-13,14,14b"),
        ("3_strategy_candidate", "4_live_ready", "G4-15"),
        ("4_live_ready", "6_published", "G5-16"),
    ]
    for src, dst, gate in chain:
        record = ledger.append(
            {
                "factor_id": fid,
                "transition": f"{src}->{dst}",
                "gate": gate,
                "evidence": {},
                "approved_by": "auto:test",
            }
        )
        # 用固定历史时间戳重写（append 自带 now，这里直接改文件行）
        path = ledger.path
        lines = path.read_text(encoding="utf-8").splitlines()
        lines[-1] = lines[-1].replace(record["timestamp"], timestamp, 1)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _set_last_timestamp(ledger, timestamp):
    """把账本最后一行的时间戳改为固定历史值（模拟早期跃迁）。"""
    path = ledger.path
    lines = path.read_text(encoding="utf-8").splitlines()
    import json as _json
    row = _json.loads(lines[-1])
    lines[-1] = lines[-1].replace(row["timestamp"], timestamp, 1)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class TestRunMonitor:
    def _setup(self, tmp_path):
        ledger = lc.EvidenceLedger(tmp_path / "evidence.jsonl")
        certs = lc.CertificateLedger(tmp_path / "certificates.json")
        return ledger, certs, tmp_path / "metrics.json", tmp_path / "report.json"

    def test_cert_expiry_auto_suspends_published_factor(self, tmp_path):
        ledger, certs, mp, rp = self._setup(tmp_path)
        _publish(ledger, "F1")
        certs.issue(_full_cert("F1", valid_until="2026-01-15T00:00:00Z"))  # 已过期

        report = mon.run_monitor(
            ledger=ledger, certs=certs, metrics_path=mp, report_path=rp, now=NOW
        )
        assert ledger.current_state("F1") == "5_suspended"
        assert ledger.has_evidence("F1", "6_published->5_suspended")
        assert any(n["kind"] == "suspend" and n["sla_due_hours"] == 24
                   for n in report["notifications"])
        assert rp.exists()

    def test_suspended_over_30d_auto_retires(self, tmp_path):
        ledger, certs, mp, rp = self._setup(tmp_path)
        _publish(ledger, "F2", timestamp="2026-01-01T00:00:00Z")
        ledger.append(
            {
                "factor_id": "F2",
                "transition": "6_published->5_suspended",
                "gate": "decay/expiry/outage",
                "evidence": {"reasons": ["测试"]},
                "approved_by": "auto:test",
            }
        )
        _set_last_timestamp(ledger, "2026-06-01T00:00:00Z")  # 挂起已 60 天
        report = mon.run_monitor(
            ledger=ledger, certs=certs, metrics_path=mp, report_path=rp,
            now=NOW,  # 挂起自 2026-01（超过 30 天）
        )
        assert ledger.current_state("F2") == "8_retired"
        assert any(n["kind"] == "retire" and n["level"] == "critical"
                   for n in report["notifications"])

    def test_decay_warning_only_watches_without_suspending(self, tmp_path):
        ledger, certs, mp, rp = self._setup(tmp_path)
        _publish(ledger, "F3")
        mp.write_text(
            '{"F3": {"listed_ic": 0.06, "rolling_12m_ic": [0.028, 0.025], "icir_12m": 0.40, "last_data_date": "2026-08-28"}}',
            encoding="utf-8",
        )
        report = mon.run_monitor(
            ledger=ledger, certs=certs, metrics_path=mp, report_path=rp, now=NOW
        )
        # 无 watch_since（观察期未满）→ 只预警，不暂停
        assert ledger.current_state("F3") == "6_published"
        assert any(n["kind"] == "watch" for n in report["notifications"])
        assert report["counts"]["watch"] == 1

    def test_deprecated_migration_countdown_notification(self, tmp_path):
        ledger, certs, mp, rp = self._setup(tmp_path)
        _publish(ledger, "F4", timestamp="2026-05-01T00:00:00Z")
        ledger.append(
            {
                "factor_id": "F4",
                "transition": "6_published->7_deprecated",
                "gate": "superseded",
                "evidence": {"reasons": ["有更优替代"]},
                "approved_by": "human:test",
            }
        )
        _set_last_timestamp(ledger, "2026-05-01T00:00:00Z")  # 迁移期 5/1 起
        report = mon.run_monitor(
            ledger=ledger, certs=certs, metrics_path=mp, report_path=rp,
            now=datetime(2026, 7, 1, tzinfo=timezone.utc),  # 迁移第 61 天
        )
        assert any(n["kind"] == "deprecate" and "29" in n["message"]
                   for n in report["notifications"])

    def test_dry_run_reports_but_keeps_state(self, tmp_path):
        ledger, certs, mp, rp = self._setup(tmp_path)
        _publish(ledger, "F5")
        certs.issue(_full_cert("F5", valid_until="2026-01-15T00:00:00Z"))
        report = mon.run_monitor(
            ledger=ledger, certs=certs, metrics_path=mp, report_path=rp,
            now=NOW, dry_run=True,
        )
        assert report["dry_run"] is True
        assert ledger.current_state("F5") == "6_published"  # 未动账本
        assert not rp.exists()

    def test_non_operated_states_ignored(self, tmp_path):
        ledger, certs, mp, rp = self._setup(tmp_path)
        ledger.append(
            {
                "factor_id": "F6",
                "transition": "1_implemented->2_validated",
                "gate": "G2-4..12",
                "evidence": {},
                "approved_by": "auto:test",
            }
        )
        report = mon.run_monitor(
            ledger=ledger, certs=certs, metrics_path=mp, report_path=rp, now=NOW
        )
        assert report["counts"]["monitored"] == 0
