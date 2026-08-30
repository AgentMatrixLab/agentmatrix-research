"""衰减监控与摘牌自动化（FACTOR_LIFECYCLE.md v2.0 运营层的代码化）。

上架不是终点——本模块把宪法「暂停、降级、退休与死亡」的量化触发条件
全部落成可执行代码：

┌──────────────────────┬──────────────────────────────────────────────────┐
│ 触发                 │ 量化条件（宪法原文）                              │
├──────────────────────┼──────────────────────────────────────────────────┤
│ 衰减预警（不改状态） │ 滚动 12 个月 Rank IC < 上架时 IC × 50%，连续 2 月 │
│ 5_suspended          │ 观察期未回升 / 12 个月 ICIR < 0.15 / 证书到期     │
│                      │ 未重验 / 数据源中断 > 5 交易日                    │
│ 8_retired（自暂停）  │ 重验失败 / 挂起超 30 天                           │
│ 8_retired（自降级）  │ deprecated 迁移期（90 天）满                      │
└──────────────────────┴──────────────────────────────────────────────────┘

SLA（写入订阅合同，本模块产出通知事件供面板/邮件消费）：
- suspended：24 小时内通知全部订阅客户
- deprecated：90 天迁移期 + 推荐替代因子
- retired：提前 30 天通知；当年摘牌 > 20% 按比例退费

输入（全部只读扫描，自动跃迁经 EvidenceLedger 留证据）：
- ``runtime/lifecycle/evidence.jsonl``     证据链（推导当前状态）
- ``runtime/lifecycle/certificates.json``  证书账本（CertificateLedger）
- ``runtime/lifecycle/decay_metrics.json`` 衰减指标（可选，见下）

``decay_metrics.json`` 契约（监控输入，由数据管线按月更新）::

    {
      "QAPI33:roe_ttm": {
        "listed_ic": 0.062,                  # 上架时（证书口径）Rank IC
        "rolling_12m_ic": [0.058, 0.028],    # 最近月起向前；末位 = 最新月
        "icir_12m": 0.41,                    # 最新滚动 12 个月 ICIR
        "last_data_date": "2026-08-28",      # 数据源最后可用交易日
        "watch_since": "2026-07-31"          # （可选）观察期起始，监控自身维护
      }
    }

输出 ``runtime/lifecycle/monitor_report.json``：
- ``notifications``：SLA 通知事件流（level/info，面板直接渲染）
- ``factors``：逐因子监控状态（watch / suspended_reasons / retire_reasons）
- ``auto_transitions``：本次自动跃迁记录（有证据链编号）

用法：
    python -X utf8 -m research_core.factor_db.lifecycle_monitor
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from common.paths import runtime_path

from research_core.factor_db.lifecycle import (
    CertificateLedger,
    EvidenceLedger,
    _now_iso,
)

LIFECYCLE_DIR = runtime_path("lifecycle")
METRICS_PATH = LIFECYCLE_DIR / "decay_metrics.json"
MONITOR_REPORT_PATH = LIFECYCLE_DIR / "monitor_report.json"

# 宪法量化常数（FACTOR_LIFECYCLE.md v2.0「暂停、降级、退休与死亡」表）
DECAY_IC_RATIO = 0.50           # 滚动 12 个月 IC < 上架时 IC 的 50%
DECAY_CONSECUTIVE_MONTHS = 2    # 且连续 2 个月
WATCH_WINDOW_DAYS = 60          # 衰减预警观察期（不改状态，暂不通知客户）
SUSPEND_ICIR_FLOOR = 0.15       # 滚动 12 个月 ICIR 下限
SUSPEND_REVALIDATE_DAYS = 30    # suspended 30 天内必须重验，否则自动 retired
DEPRECATED_MIGRATION_DAYS = 90  # deprecated 迁移期
RETIRE_ADVANCE_NOTICE_DAYS = 30 # retired 提前 30 天通知
DATA_OUTAGE_TRADING_DAYS = 5    # 数据源中断容忍（交易日）
DELISTING_REFUND_RATIO = 0.20   # 当年摘牌超订阅包 20% 触发退费条款


def _parse_iso(value: str) -> datetime:
    return datetime.strptime(value[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)


def _days_between(a: datetime, b: datetime) -> int:
    return (a - b).days


# ---------------------------------------------------------------------------
# 1. 纯判定函数（可单测，不碰 IO）
# ---------------------------------------------------------------------------

def decay_warning(listed_ic: float, rolling_12m_ic: list[float]) -> dict[str, Any]:
    """衰减预警判定：滚动 12 个月 IC < 上架时 IC × 50% 且连续 2 个月。

    ``rolling_12m_ic`` 末位为最新月。返回 {"warn": bool, "months_below": int,
    "threshold": float}；观察期进入由调用方按 ``watch_since`` 计时。
    """
    threshold = abs(listed_ic) * DECAY_IC_RATIO
    months_below = 0
    for ic in reversed(rolling_12m_ic):  # 从最新月向前数连续低于阈值月数
        if abs(ic) < threshold:
            months_below += 1
        else:
            break
    return {
        "warn": months_below >= DECAY_CONSECUTIVE_MONTHS,
        "months_below": months_below,
        "threshold": round(threshold, 6),
    }


def suspend_reasons(
    *,
    metrics: dict[str, Any] | None,
    cert_days_remaining: int | None,
    data_stale_days: int | None,
    in_watch_unrecovered: bool = False,
) -> list[str]:
    """5_suspended 的四类量化触发（宪法表：①观察期未回升 ②ICIR<0.15
    ③证书到期未重验 ④数据中断>5 交易日）。返回触发原因清单，空 = 不触发。"""
    reasons: list[str] = []
    if in_watch_unrecovered:
        reasons.append("观察期（60 天）内 IC 未回升至上架时 50% 以上")
    if metrics is not None and metrics.get("icir_12m") is not None:
        if metrics["icir_12m"] < SUSPEND_ICIR_FLOOR:
            reasons.append(
                f"滚动 12 个月 ICIR {metrics['icir_12m']:.3f} < {SUSPEND_ICIR_FLOOR}"
            )
    if cert_days_remaining is not None and cert_days_remaining < 0:
        reasons.append(f"证书到期未重验（已过期 {-cert_days_remaining} 天）")
    if data_stale_days is not None and data_stale_days > DATA_OUTAGE_TRADING_DAYS:
        reasons.append(f"数据源中断 {data_stale_days} 天 > {DATA_OUTAGE_TRADING_DAYS} 交易日")
    return reasons


def retire_reasons(state: str, since_iso: str, now: datetime) -> list[str]:
    """8_retired 的时限触发：suspended 超 30 天 / deprecated 迁移期满 90 天。"""
    reasons: list[str] = []
    since = _parse_iso(since_iso)
    days = _days_between(now, since)
    if state == "5_suspended" and days > SUSPEND_REVALIDATE_DAYS:
        reasons.append(
            f"挂起 {days} 天 > {SUSPEND_REVALIDATE_DAYS} 天未完成重验"
        )
    if state == "7_deprecated" and days > DEPRECATED_MIGRATION_DAYS:
        reasons.append(
            f"降级迁移期 {DEPRECATED_MIGRATION_DAYS} 天已满（挂起 {days} 天）"
        )
    return reasons


def sla_notification(
    factor_id: str,
    kind: str,  # suspend / retire / deprecate / watch / refund
    message: str,
    *,
    due_hours: int | None = None,
    level: str = "warning",
) -> dict[str, Any]:
    """构造 SLA 通知事件（面板渲染 + 邮件分发共用同一事件流）。"""
    return {
        "factor_id": factor_id,
        "kind": kind,
        "level": level,
        "message": message,
        "sla_due_hours": due_hours,
        "generated_at": _now_iso(),
    }


# ---------------------------------------------------------------------------
# 2. 监控主流程（扫描 → 判定 → 自动跃迁 → 报告）
# ---------------------------------------------------------------------------

def run_monitor(
    *,
    ledger: EvidenceLedger | None = None,
    certs: CertificateLedger | None = None,
    metrics_path: Path = METRICS_PATH,
    report_path: Path = MONITOR_REPORT_PATH,
    now: datetime | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """全量扫描上架后因子，执行衰减预警 / 自动暂停 / 自动退休。

    只处理 ``6_published`` / ``5_suspended`` / ``7_deprecated`` 三态的因子；
    其余状态不属运营层管辖。自动跃迁全部写证据链（dry_run 只报告不动账本）。
    """
    now = now or datetime.now(timezone.utc)
    ledger = ledger or EvidenceLedger()
    certs = certs or CertificateLedger()

    metrics_all: dict[str, dict[str, Any]] = {}
    if metrics_path.exists():
        metrics_all = json.loads(metrics_path.read_text(encoding="utf-8"))

    # 按 factor_id 汇总证据链：当前状态 + 各状态进入时间（最近一次）
    entries = ledger.entries()
    current: dict[str, str] = {}
    entered_at: dict[str, dict[str, str]] = {}
    for row in entries:
        fid = row.get("factor_id")
        if not fid:
            continue
        state = row["transition"].split("->")[1]
        current[fid] = state
        entered_at.setdefault(fid, {})[state] = row.get("timestamp", "")

    OPERATED = ("6_published", "5_suspended", "7_deprecated")
    notifications: list[dict[str, Any]] = []
    factor_status: dict[str, dict[str, Any]] = []
    auto_transitions: list[dict[str, Any]] = []

    for fid, state in sorted(current.items()):
        if state not in OPERATED:
            continue
        m = metrics_all.get(fid)
        cert_days = certs.days_remaining(fid) if certs.get(fid) else None
        data_stale = None
        if m and m.get("last_data_date"):
            data_stale = _days_between(now, _parse_iso(m["last_data_date"]))

        status: dict[str, Any] = {
            "factor_id": fid,
            "state": state,
            "cert_days_remaining": cert_days,
            "data_stale_days": data_stale,
        }

        # ── 衰减预警（仅 published；不改状态，暂不通知客户） ──
        if state == "6_published" and m and m.get("rolling_12m_ic") and m.get("listed_ic"):
            warn = decay_warning(m["listed_ic"], m["rolling_12m_ic"])
            status["decay"] = warn
            if warn["warn"]:
                status["watch"] = True
                notifications.append(
                    sla_notification(
                        fid, "watch",
                        f"滚动 12 个月 IC 连续 {warn['months_below']} 个月低于上架时 50%"
                        "（进入 60 天观察期，暂不通知客户）",
                        level="info",
                    )
                )

        # ── 自动暂停：published → suspended ──
        if state == "6_published":
            in_watch = bool(status.get("watch"))
            reasons = suspend_reasons(
                metrics=m,
                cert_days_remaining=cert_days,
                data_stale_days=data_stale,
                in_watch_unrecovered=in_watch and _watch_expired(m, now),
            )
            status["suspend_reasons"] = reasons
            if reasons:
                notifications.append(
                    sla_notification(
                        fid, "suspend",
                        "；".join(reasons) + " → 停止分发信号",
                        due_hours=24,
                    )
                )
                if not dry_run:
                    record = ledger.append(
                        {
                            "factor_id": fid,
                            "transition": "6_published->5_suspended",
                            "gate": "decay/expiry/outage",
                            "evidence": {"reasons": reasons},
                            "approved_by": "auto:lifecycle_monitor",
                        }
                    )
                    auto_transitions.append(
                        {"factor_id": fid, "transition": "6_published->5_suspended",
                         "timestamp": record["timestamp"]}
                    )
                    status["state"] = "5_suspended"
                    state = "5_suspended"
                    entered_at.setdefault(fid, {})["5_suspended"] = record["timestamp"]

        # ── 自动退休：suspended/deprecated 超时限 ──
        since = (entered_at.get(fid, {}) or {}).get(state, "")
        if state in ("5_suspended", "7_deprecated") and since:
            reasons = retire_reasons(state, since, now)
            status["retire_reasons"] = reasons
            if reasons:
                notifications.append(
                    sla_notification(
                        fid, "retire",
                        "；".join(reasons) + " → 摘牌下架，证据链永久保留",
                        due_hours=RETIRE_ADVANCE_NOTICE_DAYS * 24,
                        level="critical",
                    )
                )
                if not dry_run:
                    transition = f"{state}->8_retired"
                    record = ledger.append(
                        {
                            "factor_id": fid,
                            "transition": transition,
                            "gate": "revalidate-fail/30d" if state == "5_suspended" else "migration-90d",
                            "evidence": {"reasons": reasons},
                            "approved_by": "auto:lifecycle_monitor",
                        }
                    )
                    auto_transitions.append(
                        {"factor_id": fid, "transition": transition,
                         "timestamp": record["timestamp"]}
                    )
                    status["state"] = "8_retired"

        # ── 降级迁移期倒计时（通知用，跃迁由人工触发） ──
        if status.get("state", state) == "7_deprecated" and since:
            days_in = _days_between(now, _parse_iso(since))
            status["migration_days_remaining"] = max(
                0, DEPRECATED_MIGRATION_DAYS - days_in
            )
            notifications.append(
                sla_notification(
                    fid, "deprecate",
                    f"迁移期剩余 {status['migration_days_remaining']} 天（共 "
                    f"{DEPRECATED_MIGRATION_DAYS} 天），期满自动 retired",
                    level="warning",
                )
            )

        factor_status.append(status)

    report = {
        "generated_at": _now_iso(),
        "scanned_states": list(OPERATED),
        "counts": {
            "monitored": len(factor_status),
            "watch": sum(1 for s in factor_status if s.get("watch")),
            "suspended": sum(1 for s in factor_status if s.get("state") == "5_suspended"),
            "retired_this_run": len(
                [t for t in auto_transitions if t["transition"].endswith("8_retired")]
            ),
            "notifications": len(notifications),
        },
        "notifications": notifications,
        "factors": factor_status,
        "auto_transitions": auto_transitions,
        "dry_run": dry_run,
        "sla_policy": {
            "suspend_notice_hours": 24,
            "revalidate_deadline_days": SUSPEND_REVALIDATE_DAYS,
            "migration_days": DEPRECATED_MIGRATION_DAYS,
            "retire_notice_days": RETIRE_ADVANCE_NOTICE_DAYS,
            "refund_trigger_ratio": DELISTING_REFUND_RATIO,
        },
    }
    if not dry_run:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return report


def _watch_expired(metrics: dict[str, Any], now: datetime) -> bool:
    """观察期（60 天）是否已满仍未回升。``watch_since`` 由监控维护；
    无该字段时视为未满（首次触发预警只进观察期，下轮再判暂停）。"""
    since = metrics.get("watch_since")
    if not since:
        return False
    return _days_between(now, _parse_iso(since)) > WATCH_WINDOW_DAYS


def main() -> int:
    report = run_monitor()
    c = report["counts"]
    print(f"[monitor] 扫描 {c['monitored']} 个运营态因子："
          f"预警 {c['watch']} · 暂停 {c['suspended']} · "
          f"本轮退休 {c['retired_this_run']} · 通知 {c['notifications']}")
    for t in report["auto_transitions"]:
        print(f"  自动跃迁 {t['factor_id']} {t['transition']} @ {t['timestamp']}")
    print(f"[monitor] 报告: {MONITOR_REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
