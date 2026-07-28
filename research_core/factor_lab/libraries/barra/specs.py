"""
Barra 风险因子规格 — 从回测引擎 barra_4factor 策略提取并注册到因子实验室。

因子列表:
  BP  = total_equity / total_assets           (账面市值比)
  EY  = net_profit  / total_assets            (盈利收益率)
  Lev = -total_liabilities / total_assets     (杠杆, 取反)
  NLS = size² 对 size 回归的残差               (非线性市值)
"""

from __future__ import annotations

from contracts.factor_research import FactorResearchSpec, ValidationThreshold


BARRA_SOURCE = "Barra Risk Factors (CNE5)"
BARRA_VERSION = "v1"

BARRA_COMMON_THRESHOLDS = [
    ValidationThreshold("formula_match_ratio", ">=", 1.0, "实现与定义公式逐项一致。"),
    ValidationThreshold("cross_section_spearman", ">=", 0.95, "与回测引擎原实现做截面对齐。"),
]

BARRA_IMPLEMENTED_DETAILS: dict[int, dict[str, object]] = {
    1: {
        "formula": "total_equity / total_assets",
        "description": "账面市值比 (Book-to-Price): 净资产除以总资产, 价值因子, 值越高越便宜。",
        "required_fields": ["total_equity", "total_assets"],
        "parameters": {"clip_lower": 1},
        "notes": ["从 balance_sheet.parquet 加载总资产/净资产数据。"],
    },
    2: {
        "formula": "net_profit / total_assets",
        "description": "盈利收益率 (Earnings Yield): 净利润除以总资产, 盈利因子, 值越高盈利能力越强。",
        "required_fields": ["net_profit", "total_assets"],
        "parameters": {"clip_lower": 1, "fill_na": 0},
        "notes": ["从 income_stmt.parquet 加载净利润数据。", "净利润缺失时填 0。"],
    },
    3: {
        "formula": "-total_liabilities / total_assets",
        "description": "杠杆因子 (Leverage, 取反): 负的总负债除以总资产, 值越高杠杆越低越安全。",
        "required_fields": ["total_liabilities", "total_assets"],
        "parameters": {"clip_lower": 1},
        "notes": ["取反使高杠杆对应低得分。"],
    },
    4: {
        "formula": "size^2 - (alpha + beta * size)  # 回归残差",
        "description": "非线性市值 (Non-Linear Size): 对数市值平方对对数市值回归的残差, 捕捉极端市值效应。",
        "required_fields": ["total_assets"],
        "parameters": {"clip_lower_log": 1e6},
        "notes": [
            "size = log(total_assets), 做最小二乘回归。",
            "残差 = size² - (α + β·size)。",
        ],
    },
}


def barra_specs() -> list[FactorResearchSpec]:
    """返回所有已实现的 Barra 因子规格"""
    factor_names = {1: "BP", 2: "EY", 3: "Lev", 4: "NLS"}
    specs: list[FactorResearchSpec] = []
    for idx, detail in BARRA_IMPLEMENTED_DETAILS.items():
        fname = factor_names[idx]
        specs.append(
            FactorResearchSpec(
                factor_name=fname,
                library="barra",
                version=BARRA_VERSION,
                display_name=fname,
                factor_id=f"barra_{fname.lower()}",
                source_document=BARRA_SOURCE,
                formula=str(detail["formula"]),
                description=str(detail.get("description", "")),
                frequency="day",
                sample_scope="全A股",
                required_fields=list(detail.get("required_fields", [])),
                parameters=dict(detail.get("parameters", {})),
                validation_targets=list(BARRA_COMMON_THRESHOLDS),
                tags=["barra", "risk-factor", "fundamental"],
                notes=list(detail.get("notes", [])),
            )
        )
    return specs


IMPLEMENTED_BARRA_FACTORS = ("BP", "EY", "Lev", "NLS")
