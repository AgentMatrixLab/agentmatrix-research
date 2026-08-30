"""因子数据库元数据层。

组合多个因子来源为统一的产品级元数据目录：
- Quant API 33 因子：精编中文元数据（quant_api_33_meta.py），数据可经
  Quant API v2 factor_monthly 端点查询真实月频值。
- Alpha101 101 因子：从 research_core.factor_lab.libraries.alpha101.specs
  动态加载（单一事实源），公式与描述随仓库规格自动更新。
- qlib-factor-zoo 906 因子（zoo_meta.json，自动生成）：GTJA191（191）、
  TDXGS 通达信技术指标（88）、JQ110 技术因子（109）、Alpha158（158）、
  Alpha360 原始量价回溯（360）；因子值需 Qlib 数据环境计算。
  zoo 内 Alpha101 与本地库重复，故未重复收录。
- Barra CNE5 风格因子 11 个（BARRA）：从 factor_lab barra.py 实现动态生成。
- JQGM 换手率因子 7 个（JQGM）：从 factor_lab jq_gm specs 提取
  换手率家族（单日/5/20/60/120 日均值及短长窗之比）。

因子唯一标识符（factor_id）规则：
- ``QAPI33:<name>``     Quant API 33 因子
- ``ALPHA101:alpha<N>`` WorldQuant Alpha101 因子（N 为 1..101）
- ``GTJA191:<name>``    国泰君安 191 短线交易因子（如 GTJA191:GTJA001）
- ``TDXGS:<name>``      通达信技术指标（如 TDXGS:TDXGS_EMA_05）
- ``JQ110:<name>``      JQ110 技术因子（如 JQ110:JQ110_ROC_006）
- ``ALPHA158:<name>``   Qlib Alpha158 特征（如 ALPHA158:KMID）
- ``ALPHA360:<name>``   Qlib Alpha360 原始特征（如 ALPHA360:CLOSE59）
- ``BARRA:<name>``      Barra CNE5 风格因子（如 BARRA:size）
- ``JQGM:<name>``       换手率家族因子（如 JQGM:turnover_ratio_20d）
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

# ---------------------------------------------------------------------------
# Barra CNE5 风格因子（11 个）：唯一事实源为 factor_lab barra.py 实现。
# ---------------------------------------------------------------------------

BARRA_DATA_SOURCE = "Barra CNE5（中国A股风险模型）风格因子体系 + 本仓库 factor_lab 实现（research_core/factor_lab/libraries/barra.py）"
BARRA_FREQUENCY = "日频（计算）；风险暴露通常按月频截面使用"
BARRA_COVERAGE = "全A 标准股票池（剔除 ST/退市/上市不满窗口期）"

_BARRA_FACTOR_DEFS: tuple[dict[str, str], ...] = (
    {
        "name": "size",
        "name_cn": "规模因子（SIZE）",
        "definition": "公司规模因子：对数总市值。大市值股票与小市值股票在风险收益特征上的系统性差异。",
        "formula_expr": "ln(close * total_shares)",
        "formula_latex": r"\mathrm{SIZE} = \ln\left(P_{t} \times \mathrm{Shares}_{t}\right)",
        "logic_notes": "以收盘价乘以总股本取自然对数；A 股小市值长期存在规模溢价，是风险模型必收的风格暴露。",
        "application": "风险模型规模暴露控制、市值中性化分组、小市值 alpha 策略的基准因子。",
        "cautions": "市值缺失或停牌时需前值填充；新股上市初期市值口径需注意流通/总股本差异。",
    },
    {
        "name": "beta",
        "name_cn": "贝塔因子（BETA）",
        "definition": "个股收益对市场收益（沪深300 或等权市场组合）的 60 日滚动回归敏感度。",
        "formula_expr": "rolling_ols_beta(stock_return, market_return, 60)",
        "formula_latex": r"\beta_{i} = \dfrac{\mathrm{Cov}(r_{i}, r_{m};\,60)}{\mathrm{Var}(r_{m};\,60)}",
        "logic_notes": "市场收益缺失时退化为等权平均市场收益；窗口内样本不足时输出缺失。",
        "application": "系统性风险暴露度量、市场中性组合的 beta 对冲、低波低贝塔策略。",
        "cautions": "beta 估计受市场 regime 影响较大；停牌期间收益缺失会造成回归样本偏差。",
    },
    {
        "name": "momentum_12m1m",
        "name_cn": "动量因子（MOMENTUM）",
        "definition": "12-1 月动量：过去 12 个月累计收益剔除最近 1 个月（避免短期反转效应污染）。",
        "formula_expr": "sum(returns, 12M) - sum(returns, 1M)",
        "formula_latex": r"\mathrm{MOM}_{i} = \sum_{t=21}^{252} r_{i,t}",
        "logic_notes": "剔除最近一个月是经典动量构造，用于规避 A 股显著的月内反转效应。",
        "application": "中期趋势类策略、动量组合构建、风险模型的动量风格暴露。",
        "cautions": "A 股动量效应弱于美股且反转显著，需配合反转因子使用；除权除息需复权处理。",
    },
    {
        "name": "volatility",
        "name_cn": "波动率因子（VOLATILITY）",
        "definition": "过去 60 个交易日日收益率的标准差，度量个股总波动水平。",
        "formula_expr": "std(returns, 60)",
        "formula_latex": r"\sigma_{i} = \sqrt{\dfrac{1}{59}\sum_{t=1}^{60}\left(r_{i,t} - \bar{r}_{i}\right)^{2}}",
        "logic_notes": "采用简单滚动标准差（总波动），不做特质化拆分；年化仅在需要跨频率比较时进行。",
        "application": "低波动异象策略、风险预算分配、波动率择时。",
        "cautions": "停牌密集期波动率被低估；一二级市场联动极端行情下分布厚尾，建议配合 Winsorize。",
    },
    {
        "name": "btop",
        "name_cn": "账面市值比因子（BTOP）",
        "definition": "最新财报净资产 / 当前总市值，即 B/P 价值因子。",
        "formula_expr": "book_value / market_cap",
        "formula_latex": r"\mathrm{BTOP} = \dfrac{B_{t}}{P_{t} \times \mathrm{Shares}_{t}}",
        "logic_notes": "分子取最近披露财报的股东权益，分母取当前市值，形成价值风格暴露。",
        "application": "价值风格策略、财务与市场估值联动分析、风险模型价值维度。",
        "cautions": "财报披露滞后，需注意前视偏差（用可获得的最新已披露值）；净资产为负时因子无意义。",
    },
    {
        "name": "earnings_yield",
        "name_cn": "盈利收益率因子（EARNYILD）",
        "definition": "净利润 TTM / 当前总市值，即市盈率倒数（EP）。",
        "formula_expr": "net_profit_ttm / market_cap",
        "formula_latex": r"\mathrm{EP} = \dfrac{\mathrm{NP}_{\mathrm{TTM}}}{P_{t} \times \mathrm{Shares}_{t}}",
        "logic_notes": "盈利取滚动十二个月口径以消除季节性；为负时保留符号参与截面。",
        "application": "价值与盈利质量复合暴露、选股估值维度、风险模型盈利收益风格。",
        "cautions": "亏损股 EP 为负，截面排序时分布左偏，建议 Winsorize 或分域处理。",
    },
    {
        "name": "growth",
        "name_cn": "成长因子（GROWTH）",
        "definition": "盈利增长：净利润同比增速等成长指标的复合暴露。",
        "formula_expr": "net_profit_yoy (composite of growth metrics)",
        "formula_latex": r"\mathrm{GROWTH} = \dfrac{\mathrm{NP}_{\mathrm{TTM}} - \mathrm{NP}_{\mathrm{TTM},\,-1y}}{\left|\mathrm{NP}_{\mathrm{TTM},\,-1y}\right|}",
        "logic_notes": "CNE5 中成长由多个成长指标合成，本实现取核心盈利同比口径，避免无法从单字段精确还原复合因子。",
        "application": "成长风格策略、业绩驱动选股、风险模型成长维度。",
        "cautions": "低基数导致增速爆炸，需剔除基期近零样本；财报口径变化需回溯对齐。",
    },
    {
        "name": "leverage",
        "name_cn": "杠杆因子（LEVERAGE）",
        "definition": "负债权益比（DER），度量公司财务杠杆水平。",
        "formula_expr": "total_liability / total_equity",
        "formula_latex": r"\mathrm{LEV} = \dfrac{L_{t}}{E_{t}}",
        "logic_notes": "取最新财报资产负债表口径；部分实现采用市场杠杆（总资产/总市值）替代。",
        "application": "财务风险控制、杠杆异象研究、风险模型杠杆维度。",
        "cautions": "金融行业杠杆口径与一般行业不可比，建议分行业标准化；负净资产情形需特殊处理。",
    },
    {
        "name": "liquidity",
        "name_cn": "流动性因子（LIQUIDITY）",
        "definition": "基于换手率的流动性复合暴露：多窗口日均换手率的对数加权。",
        "formula_expr": "w1*log(avg_turnover_21d) + w2*log(avg_turnover_60d) + w3*log(avg_turnover_252d)",
        "formula_latex": r"\mathrm{LIQ} = \sum_{k} w_{k}\,\ln\left(\overline{\mathrm{Turn}}_{k}\right)",
        "logic_notes": "CNE5 用 21/60/252 日三个窗口换手率加权；权重按窗口长短设置，短窗口权重更高。",
        "application": "流动性风险管理、交易成本评估、流动性溢价策略。",
        "cautions": "换手率受流通盘口径影响；新股与热点股换手异常，需截面标准化处理。",
    },
    {
        "name": "nonlinear_size",
        "name_cn": "非线性规模因子（NLIZE）",
        "definition": "规模的立方暴露：对规模因子做残差化后的三次方项，捕捉市值与收益的非线性关系。",
        "formula_expr": "residualize(size^3, [size])",
        "formula_latex": r"\mathrm{NLIZE} = \left(\mathrm{SIZE}^{*}\right)^{3},\quad \mathrm{SIZE}^{*} \perp \mathrm{SIZE}",
        "logic_notes": "先对 SIZE 三次方再对 SIZE 自身回归取残差，保证与规模因子正交，只保留非线性部分。",
        "application": "中市值效应研究、规模维度的非线性风险暴露控制。",
        "cautions": "对极端市值敏感，建议先截面标准化再做残差化；样本较小时估计不稳定。",
    },
    {
        "name": "residual_volatility",
        "name_cn": "特质残差波动率因子（RESVOL）",
        "definition": "剥离风格与行业暴露后的残差收益波动率，度量个股特质风险。",
        "formula_expr": "std(residual_return, 60) where residual from style/industry regression",
        "formula_latex": r"\mathrm{RESVOL} = \mathrm{Std}\left(\epsilon_{i,t};\,60\right),\; r_{i,t} - \boldsymbol{\beta}^{\top}\mathbf{f}_{t} = \epsilon_{i,t}",
        "logic_notes": "简化实现可先做总波动、再对 beta/size 等主风格残差化；完整实现需滚动多因子回归。",
        "application": "特质波动率异象（低特质波动溢价）、alpha 因子纯净度评估、风险模型残差风险。",
        "cautions": "依赖风险模型解释力，回归窗口与因子集选择对结果影响大；计算成本高于其他风格因子。",
    },
)


def _build_barra_meta() -> list[dict[str, Any]]:
    """从 barra.py 因子名单生成 Barra CNE5 风格因子产品级元数据。"""
    from research_core.factor_lab.libraries.barra import BARRA_FACTOR_NAMES

    defs = {item["name"]: item for item in _BARRA_FACTOR_DEFS}
    rows: list[dict[str, Any]] = []
    for name in BARRA_FACTOR_NAMES:
        item = defs.get(name)
        if item is None:
            continue
        rows.append(
            {
                "factor_id": f"BARRA:{name}",
                "factor_lab_id": name,
                "name_cn": item["name_cn"],
                "name_en": name.upper(),
                "category": "风险因子",
                "subcategory": "风格因子",
                "data_source": BARRA_DATA_SOURCE,
                "frequency": BARRA_FREQUENCY,
                "coverage": BARRA_COVERAGE,
                "history_start": "2020-01-02（日 K 数据起始；因子值需行情与财报数据环境）",
                "definition": item["definition"],
                "calc_logic": "基于日频行情（与所需财报字段）按 Barra CNE5 口径滚动计算；月频取月末截面暴露。",
                "formula_expr": item["formula_expr"],
                "formula_latex": item["formula_latex"],
                "logic_notes": item["logic_notes"],
                "application": item["application"],
                "cautions": item["cautions"],
            }
        )
    return rows


# ---------------------------------------------------------------------------
# JQGM 换手率因子（7 个）：情绪类换手率家族，specs 为唯一事实源。
# ---------------------------------------------------------------------------

JQGM_DATA_SOURCE = "JQ/GM 风格因子体系换手率家族 + 本仓库 factor_lab 实现（research_core/factor_lab/libraries/jq_gm）"
JQGM_FREQUENCY = "日频（计算）；月频取月末截面值"
JQGM_COVERAGE = "全A 标准股票池（剔除 ST/退市/上市不满窗口期）"

_JQGM_TURNOVER_NAMES: tuple[str, ...] = (
    "turnover_ratio",
    "turnover_ratio_5d",
    "turnover_ratio_20d",
    "turnover_ratio_60d",
    "turnover_ratio_120d",
    "turnover_ratio_5d_to_120d",
    "turnover_ratio_20d_to_120d",
)

_JQGM_TURNOVER_LATEX: dict[str, str] = {
    "turnover_ratio": r"\mathrm{Turn}_{t} = \dfrac{V_{t}}{\mathrm{FloatShares}_{t}}",
    "turnover_ratio_5d": r"\overline{\mathrm{Turn}}_{5} = \dfrac{1}{5}\sum_{i=1}^{5}\mathrm{Turn}_{t-i+1}",
    "turnover_ratio_20d": r"\overline{\mathrm{Turn}}_{20} = \dfrac{1}{20}\sum_{i=1}^{20}\mathrm{Turn}_{t-i+1}",
    "turnover_ratio_60d": r"\overline{\mathrm{Turn}}_{60} = \dfrac{1}{60}\sum_{i=1}^{60}\mathrm{Turn}_{t-i+1}",
    "turnover_ratio_120d": r"\overline{\mathrm{Turn}}_{120} = \dfrac{1}{120}\sum_{i=1}^{120}\mathrm{Turn}_{t-i+1}",
    "turnover_ratio_5d_to_120d": r"\dfrac{\overline{\mathrm{Turn}}_{5}}{\overline{\mathrm{Turn}}_{120}}",
    "turnover_ratio_20d_to_120d": r"\dfrac{\overline{\mathrm{Turn}}_{20}}{\overline{\mathrm{Turn}}_{120}}",
}


def _build_jqgm_meta() -> list[dict[str, Any]]:
    """从 jq_gm specs 中提取换手率家族因子，生成产品级元数据。"""
    from research_core.factor_lab.libraries.jq_gm.specs import jq_gm_specs

    by_name = {str(spec.factor_name): spec for spec in jq_gm_specs()}
    rows: list[dict[str, Any]] = []
    for name in _JQGM_TURNOVER_NAMES:
        spec = by_name.get(name)
        if spec is None:
            continue
        display = str(spec.display_name or name)
        desc = str(spec.description or "")
        notes: list[str] = []
        if isinstance(spec.notes, list):
            notes = [str(item) for item in spec.notes]
        elif spec.notes:
            notes = [str(spec.notes)]
        rows.append(
            {
                "factor_id": f"JQGM:{name}",
                "factor_lab_id": str(spec.factor_id),
                "name_cn": display,
                "name_en": name,
                "category": "情绪因子",
                "subcategory": "换手率",
                "data_source": JQGM_DATA_SOURCE,
                "frequency": JQGM_FREQUENCY,
                "coverage": JQGM_COVERAGE,
                "history_start": "2020-01-02（日 K 数据起始；因子值需行情数据环境）",
                "definition": desc,
                "calc_logic": "基于日频换手率按对应窗口滚动均值（或窗口比值）计算；月频取月末截面值。",
                "formula_expr": desc or display,
                "formula_latex": _JQGM_TURNOVER_LATEX.get(name, ""),
                "logic_notes": "；".join(notes) if notes else desc,
                "application": (
                    "换手率是 A 股最有效的情绪/流动性代理之一：短期高换手常伴随情绪过热与反转风险，"
                    "长期低换手反映关注度不足；换手率期限结构（短窗/长窗之比）可用于捕捉交易活跃度拐点。"
                ),
                "cautions": (
                    "流通股本口径变化（限售解禁）会跳变换手率；次新股换手异常偏高，"
                    "建议截面 Winsorize 并对上市不满 120 日样本剔除长窗口因子。"
                ),
            }
        )
    return rows



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
    rows: list[dict[str, Any]] = [
        *QUANT_API_33_META,
        *_build_alpha101_meta(),
        *_load_zoo_meta(),
        *_build_barra_meta(),
        *_build_jqgm_meta(),
    ]
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
