"""因子数据库元数据层。

组合多个因子来源为统一的产品级元数据目录：
- Quant API 33 因子：精编中文元数据（quant_api_33_meta.py），数据可经
  Quant API v2 factor_monthly 端点查询真实月频值。
- Alpha101 101 因子：从 research_core.factor_lab.libraries.alpha101.specs
  动态加载（单一事实源），公式与描述随仓库规格自动更新。
- qlib-factor-zoo 906 因子（zoo_meta.json，自动生成）：GTJA191（191）、
  TDXGS 通达信技术指标（88）、JQ110 聚宽技术因子（109）、Alpha158（158）、
  Alpha360 原始量价回溯（360）；因子值需 Qlib 数据环境计算。
  zoo 内 Alpha101 与本地库重复，故未重复收录。

因子唯一标识符（factor_id）规则：
- ``QAPI33:<name>``     Quant API 33 因子
- ``ALPHA101:alpha<N>`` WorldQuant Alpha101 因子（N 为 1..101）
- ``GTJA191:<name>``    国泰君安 191 短线交易因子（如 GTJA191:GTJA001）
- ``TDXGS:<name>``      通达信技术指标（如 TDXGS:TDXGS_EMA_05）
- ``JQ110:<name>``      聚宽 110 技术因子（如 JQ110:JQ110_ROC_006）
- ``ALPHA158:<name>``   Qlib Alpha158 特征（如 ALPHA158:KMID）
- ``ALPHA360:<name>``   Qlib Alpha360 原始特征（如 ALPHA360:CLOSE59）
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from research_core.factor_db.quant_api_33_meta import QUANT_API_33_META

ALPHA101_DATA_SOURCE = "WorldQuant《101 Formulaic Alphas》论文 + 本仓库 factor_lab 实现（数据可经 RQData 拉取任务补充）"
ALPHA101_FREQUENCY = "日频（计算）；月频采样可选"
ALPHA101_COVERAGE = "全A 标准股票池（剔除 ST/退市/上市不满窗口期）"

# Alpha101 子类关键词映射：按公式主要算子特征归类，便于检索过滤。
_ALPHA101_SUBCATEGORY_RULES: list[tuple[str, str]] = [
    ("IndNeutralize", "行业中性量价"),
    ("decay_linear", "衰减加权量价"),
    ("correlation", "价量相关性"),
    ("covariance", "价量协方差"),
    ("Ts_Rank", "时序排序"),
    ("ts_rank", "时序排序"),
    ("rank", "横截面排序"),
]

# 算子名 -> LaTeX 命令映射（保留伪代码参数结构，公式保真优先）。
_LATEX_OPERATORS = {
    "rank": r"\mathrm{rank}",
    "Ts_Rank": r"\mathrm{TsRank}",
    "ts_rank": r"\mathrm{TsRank}",
    "Ts_ArgMax": r"\mathrm{TsArgMax}",
    "Ts_ArgMin": r"\mathrm{TsArgMin}",
    "ts_argmin": r"\mathrm{TsArgMin}",
    "ts_min": r"\mathrm{TsMin}",
    "ts_max": r"\mathrm{TsMax}",
    "Ts_Min": r"\mathrm{TsMin}",
    "Ts_Max": r"\mathrm{TsMax}",
    "correlation": r"\mathrm{corr}",
    "covariance": r"\mathrm{cov}",
    "stddev": r"\mathrm{std}",
    "delta": r"\Delta",
    "delay": r"\mathrm{delay}",
    "sum": r"\mathrm{sum}",
    "sign": r"\mathrm{sgn}",
    "abs": r"\left|",
    "log": r"\ln",
    "scale": r"\mathrm{scale}",
    "decay_linear": r"\mathrm{decay}",
    "SignedPower": r"\mathrm{SignedPower}",
    "IndNeutralize": r"\mathrm{IndNeutralize}",
    "adv20": r"\mathrm{adv}_{20}",
    "adv60": r"\mathrm{adv}_{60}",
    "adv5": r"\mathrm{adv}_{5}",
    "adv15": r"\mathrm{adv}_{15}",
    "returns": r"r_{t}",
    "close": r"P_{t}",
    "open": r"O_{t}",
    "high": r"H_{t}",
    "low": r"L_{t}",
    "volume": r"V_{t}",
    "vwap": r"\mathrm{vwap}_{t}",
    "cap": r"\mathrm{cap}_{t}",
}

_OPERATOR_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(name) for name in _LATEX_OPERATORS) + r")\b"
)


def formula_to_latex(formula: str) -> str:
    """把 Alpha101 伪代码公式转换为可由 KaTeX 渲染的 LaTeX 记法。

    采用“数学排版的算子记法”：算子名转 \\mathrm 命令，字段名转为记号，
    保留原始参数结构以便与论文公式逐项对照。
    """
    if not formula:
        return ""

    def _replace(match: re.Match[str]) -> str:
        return _LATEX_OPERATORS[match.group(0)]

    latex = _OPERATOR_PATTERN.sub(_replace, formula.strip())
    latex = latex.replace(" ?", r"\;?\;").replace(":", r"\;:\;")
    latex = latex.replace("*", r"\cdot ").replace("/", r"/")
    return latex


def _alpha101_subcategory(formula: str) -> str:
    for keyword, subcategory in _ALPHA101_SUBCATEGORY_RULES:
        if keyword in formula:
            return subcategory
    return "复合量价"


def _build_alpha101_meta() -> list[dict[str, Any]]:
    """从 factor_lab Alpha101 规格动态生成产品级元数据。"""
    from research_core.factor_lab.libraries.alpha101.specs import alpha101_specs

    rows: list[dict[str, Any]] = []
    for spec in alpha101_specs():
        idx = int(str(spec.factor_name).replace("alpha", ""))
        formula = str(spec.formula or "")
        notes = list(spec.parameters.get("notes", []) or []) if isinstance(spec.parameters, dict) else []
        if isinstance(spec.notes, list):
            notes = [str(item) for item in spec.notes]
        fields = ", ".join(str(field) for field in spec.required_fields)
        rows.append(
            {
                "factor_id": f"ALPHA101:alpha{idx}",
                "factor_lab_id": spec.factor_id,
                "name_cn": f"WorldQuant Alpha#{idx}",
                "name_en": f"Alpha#{idx} (WorldQuant 101 Formulaic Alphas)",
                "category": "技术因子",
                "subcategory": _alpha101_subcategory(formula),
                "data_source": ALPHA101_DATA_SOURCE,
                "frequency": ALPHA101_FREQUENCY,
                "coverage": ALPHA101_COVERAGE,
                "history_start": "2020-01-02（日 K 数据起始；因子值需 RQData 拉取任务生成）",
                "definition": str(spec.description or ""),
                "calc_logic": (
                    f"基于日频行情字段（{fields}）按公式逐日计算；"
                    "月频取月末截面值。窗口参数见 factors.py 实现。"
                ),
                "formula_expr": formula,
                "formula_latex": formula_to_latex(formula),
                "logic_notes": "；".join(str(note) for note in notes) if notes else spec.description or "",
                "application": (
                    "WorldQuant 101 量价因子体系，用于短周期 alpha 组合构建、"
                    "多因子模型量价维度增强、因子挖掘基准对照。"
                ),
                "cautions": (
                    "公式中的 rank/correlation 等算子口径与实现强相关，"
                    "跨源比对需先核对算子定义（见 factor_lab operators.py）；"
                    "行业中性类因子依赖行业分类字段；日频计算成本较高，建议采样使用。"
                ),
            }
        )
    return rows


_ZOO_META_PATH = Path(__file__).resolve().parent / "zoo_meta.json"


@lru_cache(maxsize=1)
def _load_zoo_meta() -> tuple[dict[str, Any], ...]:
    """加载 qlib-factor-zoo 因子库元数据（zoo_meta.json，自动生成）。

    文件缺失时返回空元组（目录退化为原有来源，不阻断服务）。
    """
    if not _ZOO_META_PATH.is_file():
        return ()
    payload = json.loads(_ZOO_META_PATH.read_text(encoding="utf-8"))
    return tuple(payload.get("factors") or [])


@lru_cache(maxsize=1)
def _all_factors() -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = [*QUANT_API_33_META, *_build_alpha101_meta(), *_load_zoo_meta()]
    return tuple(rows)


def list_factors(
    *,
    category: str | None = None,
    subcategory: str | None = None,
    source: str | None = None,
    search: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """按条件检索因子目录，返回 (因子列表, 总数)。

    search 匹配：中文名 / 英文名 / factor_id / 定义 / 公式（大小写不敏感）。
    """
    rows = list(_all_factors())

    if category:
        rows = [row for row in rows if row["category"] == category]
    if subcategory:
        rows = [row for row in rows if row["subcategory"] == subcategory]
    if source:
        key = source.lower()
        rows = [row for row in rows if key in row["factor_id"].lower() or key in row["data_source"].lower()]
    if search:
        needle = search.strip().lower()
        if needle:
            def _hit(row: dict[str, Any]) -> bool:
                haystack = " ".join(
                    str(row.get(key, ""))
                    for key in ("name_cn", "name_en", "factor_id", "definition", "formula_expr", "subcategory")
                ).lower()
                return needle in haystack

            rows = [row for row in rows if _hit(row)]

    rows.sort(key=lambda row: (row["category"], row["factor_id"]))
    total = len(rows)
    if offset:
        rows = rows[offset:]
    if limit is not None:
        rows = rows[:limit]
    return rows, total


def get_factor(factor_id: str) -> dict[str, Any] | None:
    """按唯一标识符取因子详情。支持不带前缀的短名（仅限唯一时）。"""
    factor_id = factor_id.strip()
    for row in _all_factors():
        if row["factor_id"] == factor_id:
            return row
    # 短名兼容：如 "roe_ttm" -> "QAPI33:roe_ttm"
    candidates = [row for row in _all_factors() if row["factor_id"].split(":", 1)[-1] == factor_id]
    if len(candidates) == 1:
        return candidates[0]
    return None


def get_stats() -> dict[str, Any]:
    """因子目录统计：总数 / 分类分布 / 来源分布。"""
    rows = list(_all_factors())
    by_category: dict[str, int] = {}
    by_subcategory: dict[str, int] = {}
    by_source: dict[str, int] = {}
    for row in rows:
        by_category[row["category"]] = by_category.get(row["category"], 0) + 1
        by_subcategory[f"{row['category']}/{row['subcategory']}"] = (
            by_subcategory.get(f"{row['category']}/{row['subcategory']}", 0) + 1
        )
        source_key = row["factor_id"].split(":", 1)[0]
        by_source[source_key] = by_source.get(source_key, 0) + 1
    return {
        "total_factors": len(rows),
        "by_category": by_category,
        "by_subcategory": by_subcategory,
        "by_source": by_source,
        "factors_with_live_data": by_source.get("QAPI33", 0),
    }


def dictionary_rows() -> list[dict[str, Any]]:
    """数据字典行：每因子一行，用于导出与文档生成。"""
    return [
        {
            "factor_id": row["factor_id"],
            "name_cn": row["name_cn"],
            "name_en": row["name_en"],
            "category": row["category"],
            "subcategory": row["subcategory"],
            "data_source": row["data_source"],
            "frequency": row["frequency"],
            "coverage": row["coverage"],
            "history_start": row["history_start"],
            "formula_expr": row["formula_expr"],
            "formula_latex": row["formula_latex"],
            "definition": row["definition"],
            "application": row["application"],
            "cautions": row["cautions"],
        }
        for row in _all_factors()
    ]
