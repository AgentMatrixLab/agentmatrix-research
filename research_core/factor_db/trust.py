"""因子信任分级（trust tier）注册表。

回答一个核心问题：**这个因子凭什么可信？**

分级口径（诚实优先，宁缺勿滥）：

- ``S`` truth-proofed     官方真值 CSV 对照通过（max_abs_diff≈0）。
- ``A`` verified          G2 九道验真闸门（闸门4—12）全部通过：数据质量、可执行性、
                          IC 稳定性(bootstrap)、多重检验校正(DSR/FDR)、OOS 留存、
                          成本韧性、风格中性、市场分段、冗余去重。
- ``B`` internal          真实数据已接入（Quant API 月频真值），但尚未跑完九道验真。
- ``C`` mock-only         仅在 mock 数据（30 股×300 天，seed=42）上完成计算逻辑
                          验证；因子值未在真实数据上产出。mock 下的 constant /
                          all_nan 属于横截面算子单票退化，不降级，但如实标注。
- ``D`` rejected          源库缺陷（表达式损坏、重复定义、参数缺失）或验证失败。

口径与 docs/FACTOR_LIFECYCLE.md v2.0 对齐：tier 是 v2.0 状态机的内部视图
（S→implemented+S 级证据，A→validated，B→validated 前排队，C→implemented，
D→rejected）。

证据来源：
- 目录：research_core.factor_db.metadata（1040 因子）
- mock 验证：runtime/zoo_mock/out/report.json（1007 因子，含 failures/defects）
- 未来：G2 九道验真 runner 的结果可直接写入 evidence 并升级 tier。

模块无副作用、可缓存；7×24 挖掘循环复验后调用 :func:`build_trust_registry`
重新生成，前端面板只读该注册表。
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from common.paths import runtime_path
from research_core.factor_db.metadata import _all_factors

ZOO_REPORT_PATH = runtime_path("zoo_mock", "out", "report.json")

TIER_ORDER = ("S", "A", "B", "C", "D")

TIER_DEFINITIONS: dict[str, dict[str, str]] = {
    "S": {
        "label": "真值对照通过",
        "color": "#8b5cf6",
        "desc": "官方真值 CSV 逐因子比对通过（max_abs_diff≈0），可视为公式实现无偏差。",
    },
    "A": {
        "label": "九道验真通过",
        "color": "#10b981",
        "desc": "G2 闸门4—12 全过：数据质量 + 可执行性(涨跌停/停牌/ST/流动性) + IC稳定性(bootstrap) + 多重检验校正(DSR/FDR) + OOS留存≥70% + 成本韧性 + 风格中性 + 市场分段 + 冗余去重。",
    },
    "B": {
        "label": "真实数据已接入",
        "color": "#3b82f6",
        "desc": "因子值可经真实数据源（Quant API 月频）查询，但尚未完成九道验真。可用作研究输入，不构成投产依据。",
    },
    "C": {
        "label": "仅 mock 验证",
        "color": "#f59e0b",
        "desc": "仅在 mock 数据（30 股×300 天）上完成计算逻辑验证，max_diff=0 对照基准；因子值未在真实数据上产出，禁止直接进策略。",
    },
    "D": {
        "label": "缺陷/淘汰",
        "color": "#ef4444",
        "desc": "源库表达式损坏、重复定义、参数缺失，或验证失败。保留记录用于反馈挖掘循环。",
    },
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_zoo_report() -> dict[str, Any]:
    if not ZOO_REPORT_PATH.is_file():
        return {}
    try:
        return json.loads(ZOO_REPORT_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _mock_name(factor_id: str) -> tuple[str, str]:
    """factor_id -> (mock 库名, mock 因子名)。

    例：``GTJA191:GTJA157`` -> ("GTJA191", "GTJA157")；
    ``ALPHA101:alpha2``  -> ("ALPHA101", "ALPHA002")。
    """
    lib, name = factor_id.split(":", 1)
    if lib == "ALPHA101":
        digits = re.sub(r"\D", "", name)
        return lib, f"ALPHA{int(digits):03d}"
    return lib, name


def _mock_evidence(lib: str, name: str, report: dict[str, Any]) -> tuple[str | None, list[str]]:
    """返回 (tier 降级标记, 证据列表)。

    - failures 命中 -> D
    - zoo_defects 中“无法修复/重复定义”级缺陷命中 -> D
    - constant/all_nan -> 保持 C，证据如实标注（横截面算子单票 mock 退化）
    """
    evidence: list[str] = []
    per_lib = report.get("per_lib", {}).get(lib, {})
    failures = {f.get("name") for f in per_lib.get("failures", [])}
    if name in failures:
        detail = next(
            (f.get("error", "") for f in per_lib.get("failures", []) if f.get("name") == name),
            "",
        )
        evidence.append(f"mock_fail: {detail[:120]}")
        return "D", evidence

    for defect in report.get("zoo_defects", []):
        factors_field = str(defect.get("factor", ""))
        issue = str(defect.get("issue", ""))
        # "GTJA191/GTJA157" / "ALPHA101/ALPHA002" / "GTJA191/GTJA043|059|084"
        if "/" not in factors_field:
            continue
        dlib, dnames = factors_field.split("/", 1)
        if dlib != lib:
            continue
        for dn in dnames.split("|"):
            if dn.strip() == name and any(
                kw in issue for kw in ("损坏", "无法自动修复", "重复定义", "源库缺陷")
            ):
                evidence.append(f"zoo_defect: {issue[:120]}")
                return "D", evidence

    if name in per_lib.get("constant_examples", []):
        evidence.append("mock_constant: 横截面算子在单票 mock 下退化为常数（真实截面数据下不成立）")
    return None, evidence


def build_trust_registry() -> dict[str, Any]:
    """生成全量信任分级注册表（覆盖因子目录全部因子）。"""
    report = _load_zoo_report()
    factors: list[dict[str, Any]] = []
    tier_counts = {t: 0 for t in TIER_ORDER}
    by_source: dict[str, dict[str, int]] = {}

    for row in _all_factors():
        factor_id: str = row["factor_id"]
        source = factor_id.split(":", 1)[0]
        evidence: list[str] = []
        tier = "C"

        if source == "QAPI33":
            tier = "B"
            evidence.append("real_data: Quant API 月频真值可查（需 token）")
        else:
            lib, mock_name = _mock_name(factor_id)
            evidence.append(f"mock_run: zoo_mock {lib}/{mock_name}（30 股×300 天，seed=42）")
            downgrade, mock_ev = _mock_evidence(lib, mock_name, report)
            evidence.extend(mock_ev)
            if downgrade:
                tier = downgrade

        tier_counts[tier] += 1
        by_source.setdefault(source, {t: 0 for t in TIER_ORDER})[tier] += 1
        factors.append(
            {
                "factor_id": factor_id,
                "name_cn": row.get("name_cn", ""),
                "name_en": row.get("name_en", ""),
                "category": row.get("category", ""),
                "source": source,
                "tier": tier,
                "evidence": evidence,
            }
        )

    factors.sort(key=lambda f: (TIER_ORDER.index(f["tier"]), f["factor_id"]))
    return {
        "generated_at": _now_iso(),
        "tier_definitions": TIER_DEFINITIONS,
        "tier_order": list(TIER_ORDER),
        "tier_counts": tier_counts,
        "by_source": by_source,
        "mock_meta": report.get("meta", {}),
        "verification_gates": {
            "gates_passed_max": 0,
            "note": "G2 九道验真闸门（v2.0 闸门4—12）尚未实施；S/A 当前为 0 是如实反映，不是缺数据。",
        },
        "factors": factors,
    }
