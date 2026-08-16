"""
Factor MISMATCH diagnostic engine — 12 root-cause detectors.

Ported from CrossvalidationTYD pipeline_package/auto_diagnostic.py (v78).
Detects: cascading_failure, unit_scale, date_semantics, dimension_error,
volatility_annualization, ttm_conversion, formula_diff, data_source_diff,
path_dependency, trading_calendar, early_filer, unknown.

Usage:
    from research_core.factor_lab.diagnostics import MismatchDiagnostician

    diag = MismatchDiagnostician()
    results = diag.diagnose_all(comparison_df)
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from enum import Enum, auto
from typing import Any, Optional

import numpy as np
import pandas as pd


class RootCause(Enum):
    CASCADING_FAILURE = auto()
    UNIT_SCALE = auto()
    DATE_SEMANTICS = auto()
    DIMENSION_ERROR = auto()
    VOLATILITY_ANNUALIZATION = auto()
    TTM_CONVERSION = auto()
    FORMULA_DIFF = auto()
    DATA_SOURCE_DIFF = auto()
    PATH_DEPENDENCY = auto()
    TRADING_CALENDAR = auto()
    EARLY_FILER = auto()
    UNKNOWN = auto()


@dataclass
class Diagnosis:
    factor_name: str
    display_name: str = ""
    mismatch_count: int = 0
    high_diff: int = 0
    medium_diff: int = 0
    low_diff: int = 0
    root_cause: RootCause = RootCause.UNKNOWN
    detail: str = ""
    confidence: float = 0.0
    fix: str = ""
    difficulty: str = ""
    action: str = ""
    samples: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["root_cause"] = self.root_cause.name
        return d


class MismatchDiagnostician:
    """Auto-diagnose MISMATCH root causes using 12 pattern detectors."""

    UNIT_HIGH = 50
    UNIT_LOW = 0.02
    EARLY_FILER_MIN = 5
    CONF_HIGH = 0.9
    CONF_MED = 0.6
    CONF_LOW = 0.3

    def diagnose_all(
        self,
        comparison_df: pd.DataFrame,
        factor_registry: dict | None = None,
    ) -> dict[str, Diagnosis]:
        mismatches = comparison_df[comparison_df["status"] == "MISMATCH"].copy()
        if mismatches.empty:
            return {}

        by_factor = mismatches.groupby("factor_key")
        results: dict[str, Diagnosis] = {}
        for fk, entries in by_factor:
            results[fk] = self._diagnose(fk, entries, factor_registry or {})
        return results

    def _diagnose(
        self, factor_key: str, entries: pd.DataFrame, registry: dict
    ) -> Diagnosis:
        d = Diagnosis(factor_name=factor_key)
        d.mismatch_count = len(entries)
        meta = registry.get(factor_key, {})
        d.display_name = meta.get("display_name", factor_key)

        d.high_diff = int((entries["diff_pct"] > 0.5).sum())
        d.medium_diff = int(((entries["diff_pct"] > 0.1) & (entries["diff_pct"] <= 0.5)).sum())
        d.low_diff = int((entries["diff_pct"] <= 0.1).sum())

        d.samples = (
            entries.head(10)[["symbol", "gm_value", "jq_value", "diff_pct"]]
            .to_dict("records")
        )

        detectors = [
            self._detect_cascading,
            self._detect_unit_scale,
            self._detect_ttm,
            self._detect_date_semantics,
            self._detect_dimension,
            self._detect_volatility_annualization,
            self._detect_formula,
            self._detect_structural_diff,
            self._detect_data_source,
            self._detect_stock_level,
            self._detect_path_dependency,
            self._detect_calendar,
            self._detect_early_filer,
        ]

        for det in detectors:
            result = det(factor_key, entries, meta)
            if result:
                d.root_cause = result["category"]
                d.detail = result["detail"]
                d.confidence = result["confidence"]
                d.fix = result["fix"]
                d.difficulty = result["difficulty"]
                d.action = result["action"]
                return d

        d.root_cause = RootCause.UNKNOWN
        d.detail = "无法自动识别根因，需手工排查"
        d.fix = "建议手工对比 JQ 和 GM 的原始数据"
        d.difficulty = "medium"
        d.action = "manual_check"
        return d

    # ── Detectors ──

    def _detect_cascading(self, fk: str, e: pd.DataFrame, m: dict) -> dict | None:
        gm_nan = e["gm_value"].isna().mean()
        jq_ok = e["jq_value"].notna().mean()
        if gm_nan > 0.9 and jq_ok > 0.5:
            api = m.get("api_name", m.get("gm_field", ""))
            return {
                "category": RootCause.CASCADING_FAILURE,
                "detail": (
                    f"疑似级联 API 失败: GM {fk} 全 NaN，JQ 有值。"
                    f"可能原因: {api} 无效字段、balance_pt 超 20 字段、字段映射错误"
                ),
                "confidence": self.CONF_HIGH if gm_nan > 0.95 else self.CONF_MED,
                "fix": "检查字段名有效性; balance_pt 字段数 ≤20; 单字段验证 API",
                "difficulty": "medium",
                "action": "manual_check",
            }
        return None

    def _detect_unit_scale(self, fk: str, e: pd.DataFrame, m: dict) -> dict | None:
        v = e[(e["gm_value"].notna()) & (e["jq_value"].notna())]
        v = v[(abs(v["jq_value"]) > 1e-10) & (abs(v["gm_value"]) > 1e-10)]
        if v.empty:
            return None
        ratios = v["gm_value"] / v["jq_value"]
        avg, std = ratios.mean(), ratios.std()
        if std > abs(avg) * 0.3:
            return None
        if avg > self.UNIT_HIGH:
            return {
                "category": RootCause.UNIT_SCALE,
                "detail": f"GM 约 JQ 的 {avg:.0f}x，疑 unit_scale 缺失或需 /{avg:.0f}",
                "confidence": self.CONF_HIGH if std < abs(avg) * 0.1 else self.CONF_MED,
                "fix": f"添加 unit_scale=1/{avg:.0f}",
                "difficulty": "easy",
                "action": "modify_code",
            }
        if 0 < avg < self.UNIT_LOW:
            mul = 1.0 / avg
            return {
                "category": RootCause.UNIT_SCALE,
                "detail": f"GM 仅 JQ 的 {avg:.4f}x，疑 unit_scale={mul:.0f} 缺失",
                "confidence": self.CONF_HIGH if std < abs(avg) * 0.1 else self.CONF_MED,
                "fix": f"添加 unit_scale={mul:.0f}",
                "difficulty": "easy",
                "action": "modify_code",
            }
        return None

    def _detect_ttm(self, fk: str, e: pd.DataFrame, m: dict) -> dict | None:
        """Detect TTM stable ratio using median (robust to outliers).
        Features: median GM/JQ in 0.55-0.85, MAD/median < 0.25 → ~28% TTM diff."""
        v = e[(e["gm_value"].notna()) & (e["jq_value"].notna())]
        v = v[(abs(v["jq_value"]) > 1e-10) & (abs(v["gm_value"]) > 1e-10)]
        if v.empty:
            return None
        ratios = v["gm_value"] / v["jq_value"]
        med = ratios.median()
        mad = (ratios - med).abs().median()
        cv = mad / abs(med) if abs(med) > 1e-10 else 99
        if cv < 0.25 and 0.55 < med < 0.85:
            return {
                "category": RootCause.TTM_CONVERSION,
                "detail": f"median GM/JQ={med:.2f}(MAD={mad:.3f}), ~{abs(1-med)*100:.0f}% TTM系统差异",
                "confidence": self.CONF_HIGH if cv < 0.10 else self.CONF_MED,
                "fix": "GM自算TTM vs JQ直接TTM口径不同, 标因子级NC",
                "difficulty": "irreparable",
                "action": "mark_nc",
            }
        return None

    def _detect_date_semantics(self, fk: str, e: pd.DataFrame, m: dict) -> dict | None:
        is_ttm = m.get("ttm") or m.get("ttm_growth_v2")
        is_growth = "growth" in fk.lower() or "yoy" in fk.lower()
        if not (is_ttm or is_growth or m.get("formula")):
            return None
        v = e[(e["gm_value"].notna()) & (e["jq_value"].notna())]
        if v.empty:
            return None
        diffs = v["gm_value"] - v["jq_value"]
        pos = (diffs > 0).mean()
        if pos > 0.85 or pos < 0.15:
            return {
                "category": RootCause.DATE_SEMANTICS,
                "detail": f"{pos*100:.0f}% 同向偏差，疑 date 语义差异（公告日 vs 报告期）",
                "confidence": self.CONF_MED if abs(pos - 0.5) > 0.3 else self.CONF_LOW,
                "fix": "检查 _pt API date 参数语义; 增长率因子考虑 JQ statDate 交叉验证",
                "difficulty": "medium",
                "action": "manual_check",
            }
        return None

    def _detect_dimension(self, fk: str, e: pd.DataFrame, m: dict) -> dict | None:
        v = e[(e["gm_value"].notna()) & (e["jq_value"].notna())]
        v = v[(abs(v["jq_value"]) > 1e-10) & (abs(v["gm_value"]) > 1e-10)]
        if v.empty:
            return None
        signs = np.sign(v["gm_value"]) * np.sign(v["jq_value"])
        neg = (signs < 0).mean()
        if neg > 0.85:
            return {
                "category": RootCause.DIMENSION_ERROR,
                "detail": f"{neg*100:.0f}% 符号相反，疑公式符号翻转或维度错位",
                "confidence": self.CONF_HIGH,
                "fix": "检查 REVS 公式: close[-period-1:] vs close[-period:]; 符号约定",
                "difficulty": "easy",
                "action": "modify_code",
            }
        return None

    def _detect_volatility_annualization(self, fk: str, e: pd.DataFrame, m: dict) -> dict | None:
        if not any(kw in fk.lower() for kw in ["volatility", "std", "vol"]):
            return None
        v = e[(e["gm_value"].notna()) & (e["jq_value"].notna())]
        v = v[(abs(v["jq_value"]) > 1e-10) & (abs(v["gm_value"]) > 1e-10)]
        if v.empty:
            return None
        ratios = v["gm_value"] / v["jq_value"]
        avg, std = ratios.mean(), ratios.std()
        s = math.sqrt(252)
        if 0.05 < avg < 0.08 and std < avg * 0.3:
            return {
                "category": RootCause.VOLATILITY_ANNUALIZATION,
                "detail": f"GM/JQ≈{avg:.4f}(≈1/sqrt(252)={1/s:.4f})，疑缺少 *√252 年化",
                "confidence": self.CONF_HIGH,
                "fix": "volatility 计算添加 *np.sqrt(252)",
                "difficulty": "easy",
                "action": "modify_code",
            }
        if 14 < avg < 18 and std < avg * 0.3:
            return {
                "category": RootCause.VOLATILITY_ANNUALIZATION,
                "detail": f"GM/JQ≈{avg:.1f}(≈sqrt(252)={s:.1f})，疑重复年化",
                "confidence": self.CONF_HIGH,
                "fix": "移除多余的 *np.sqrt(252)",
                "difficulty": "easy",
                "action": "modify_code",
            }
        return None

    def _detect_formula(self, fk: str, e: pd.DataFrame, m: dict) -> dict | None:
        if not (m.get("gm_field") == "custom" or m.get("formula")):
            return None
        v = e[(e["gm_value"].notna()) & (e["jq_value"].notna())]
        if v.empty:
            return None
        diffs = v["gm_value"] - v["jq_value"]
        pos = (diffs > 0).mean()
        if pos > 0.8 or pos < 0.2:
            return {
                "category": RootCause.FORMULA_DIFF,
                "detail": f"自定义因子 {fk}, {pos*100:.0f}% 同向偏差, GM/JQ 公式可能不同",
                "confidence": self.CONF_MED,
                "fix": f"对比 GM formula 与 JQ 定义文档",
                "difficulty": "medium",
                "action": "manual_check",
            }
        return None

    def _detect_structural_diff(self, fk: str, e: pd.DataFrame, m: dict) -> dict | None:
        """Structural definition difference: large, unstable ratio."""
        v = e[(e["gm_value"].notna()) & (e["jq_value"].notna())]
        v = v[(abs(v["jq_value"]) > 1e-10) & (abs(v["gm_value"]) > 1e-10)]
        if v.empty:
            return None
        ratios = v["gm_value"] / v["jq_value"]
        med = ratios.median()
        mad = (ratios - med).abs().median()
        cv = mad / abs(med) if abs(med) > 1e-10 else 99
        if cv > 0.25 and (med < 0.4 or med > 2.5):
            return {
                "category": RootCause.FORMULA_DIFF,
                "detail": f"med ratio={med:.1f}(cv={cv:.1f}), 结构性定义差异, GM/JQ口径根本不同",
                "confidence": self.CONF_MED,
                "fix": "定义根本不同, 标因子级NC",
                "difficulty": "irreparable",
                "action": "mark_nc",
            }
        return None

    def _detect_data_source(self, fk: str, e: pd.DataFrame, m: dict) -> dict | None:
        api = m.get("api_name", m.get("gm_field", ""))
        if "balance" not in api.lower():
            return None
        if len(e) <= 20:
            return {
                "category": RootCause.DATA_SOURCE_DIFF,
                "detail": f"资产负债表因子 {fk}, {len(e)} 条 MISMATCH, 疑数据源差异",
                "confidence": self.CONF_MED if len(e) <= 10 else self.CONF_LOW,
                "fix": "无法修复（数据源级别差异），建议标 stock-level NC",
                "difficulty": "irreparable",
                "action": "mark_stock_nc",
            }
        return None

    def _detect_stock_level(self, fk: str, e: pd.DataFrame, m: dict) -> dict | None:
        """Stock-level minority mismatch: <30 total, all diffs <30%."""
        n = len(e)
        if n == 0 or n >= 30:
            return None
        low = (e["diff_pct"] < 0.10).sum()
        modest = ((e["diff_pct"] >= 0.10) & (e["diff_pct"] < 0.30)).sum()
        if low + modest == n:
            return {
                "category": RootCause.DATA_SOURCE_DIFF,
                "detail": f"{n} 条少数股票差异(diff<30%), {low}条<10%, 疑数据源/日历差异",
                "confidence": self.CONF_MED if n < 20 else self.CONF_LOW,
                "fix": "不可修复（数据源级别差异），标 stock-level NC",
                "difficulty": "irreparable",
                "action": "mark_stock_nc",
            }
        return None

    def _detect_path_dependency(self, fk: str, e: pd.DataFrame, m: dict) -> dict | None:
        kw = ["rsi", "obv", "pvt", "macd", "kdj"]
        if not any(k in fk.lower() for k in kw):
            return None
        v = e[(e["gm_value"].notna()) & (e["jq_value"].notna())]
        if v.empty:
            return None
        return {
            "category": RootCause.PATH_DEPENDENCY,
            "detail": f"路径依赖因子 {fk}, {len(v)} MISMATCH, 起算点/EWM 不同",
            "confidence": self.CONF_HIGH,
            "fix": "不可修复，标因子级 NC",
            "difficulty": "irreparable",
            "action": "mark_nc",
        }

    def _detect_calendar(self, fk: str, e: pd.DataFrame, m: dict) -> dict | None:
        cal_kw = ["momentum", "revs", "reversal", "ma", "std"]
        path_kw = ["rsi", "obv", "pvt", "macd"]
        if not any(k in fk.lower() for k in cal_kw):
            return None
        if any(k in fk.lower() for k in path_kw):
            return None
        v = e[(e["gm_value"].notna()) & (e["jq_value"].notna())]
        if v.empty:
            return None
        diffs = v["diff_pct"]
        in_range = diffs[(diffs > 0.04) & (diffs < 0.50)]
        if len(in_range) == len(v) and len(v) < 30:
            return {
                "category": RootCause.TRADING_CALENDAR,
                "detail": f"{len(v)} MISMATCH, 差异 {diffs.min()*100:.1f}%-{diffs.max()*100:.1f}%, 疑 250vs252 交易日/qfq",
                "confidence": self.CONF_MED,
                "fix": "不可修复，标 stock-level NC",
                "difficulty": "irreparable",
                "action": "mark_stock_nc",
            }
        return None

    def _detect_early_filer(self, fk: str, e: pd.DataFrame, m: dict) -> dict | None:
        is_growth = "growth" in fk.lower() or "ttm_growth" in fk.lower() or m.get("ttm_growth_v2")
        if not is_growth:
            return None
        if len(e) < self.EARLY_FILER_MIN:
            return None
        stock_counts = e.groupby("symbol").size()
        if stock_counts.max() >= 1 and len(stock_counts) < len(e) * 0.5:
            return {
                "category": RootCause.EARLY_FILER,
                "detail": f"增长率 {fk}, {len(e)} MISMATCH 集中在 {len(stock_counts)} 只, 疑 early filer",
                "confidence": self.CONF_MED,
                "fix": "JQ statDate 强制取季度数据交叉验证",
                "difficulty": "medium",
                "action": "manual_check",
            }
        return None

    # ── Reporting ──

    def generate_report(self, results: dict[str, Diagnosis]) -> str:
        if not results:
            return "# MISMATCH 诊断\n\n✅ 无 MISMATCH。"

        lines = ["# MISMATCH 自动诊断", "", f"{len(results)} 个因子:", ""]

        by_cause: dict[str, list[Diagnosis]] = defaultdict(list)
        for r in results.values():
            by_cause[r.root_cause.name].append(r)

        for cause, group in by_cause.items():
            lines.append(f"## {cause} ({len(group)})")
            lines.append("| 因子 | 数 | 高/中/低 | 信 | 建议 | 详情 |")
            lines.append("|---|---:|---:|---:|---:|---|")
            for r in sorted(group, key=lambda x: -x.mismatch_count):
                lines.append(
                    f"| {r.factor_name} | {r.mismatch_count} | "
                    f"{r.high_diff}/{r.medium_diff}/{r.low_diff} | "
                    f"{r.confidence:.0%} | {r.action} | {r.detail[:60]} |"
                )
            lines.append("")

        return "\n".join(lines)
