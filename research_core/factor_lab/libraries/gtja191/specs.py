from __future__ import annotations

from contracts.factor_research import FactorResearchSpec, ValidationThreshold


GTJA191_SOURCE = "国泰君安短周期价量 Alpha191"
GTJA191_VERSION = "v2026.06"
GTJA191_COMMON_THRESHOLDS = [
    ValidationThreshold("formula_match_ratio", ">=", 1.0, "代码实现与规格书公式逐项一致。"),
    ValidationThreshold("field_mapping_match_ratio", ">=", 1.0, "字段、复权、频率和股票池口径一致。"),
    ValidationThreshold("sample_point_error_ratio", "<=", 0.0, "抽样点位误差为零。"),
    ValidationThreshold("cross_section_spearman", ">=", 0.99, "与外部真值做截面对齐。"),
]


GTJA191_IMPLEMENTED_DETAILS: dict[int, dict[str, object]] = {
    1: {
        "formula": "(-1 * CORR(RANK(DELTA(LOG(VOLUME), 1)), RANK((CLOSE - OPEN) / OPEN), 6))",
        "description": "成交量对数变化排序与日内收益排序的 6 日相关反向因子。",
        "required_fields": ["open", "close", "volume"],
        "parameters": {"delta_window": 1, "corr_window": 6},
    },
    2: {
        "formula": "(-1 * DELTA((((CLOSE - LOW) - (HIGH - CLOSE)) / (HIGH - LOW)), 1))",
        "description": "日内价格强弱位置的一日变化反向因子。",
        "required_fields": ["high", "low", "close"],
        "parameters": {"delta_window": 1},
    },
    3: {
        "formula": "SUM(conditioned close-prev-close effective move, 6)",
        "description": "按涨跌条件构造有效价格移动并做 6 日求和。",
        "required_fields": ["high", "low", "close"],
        "parameters": {"sum_window": 6},
    },
    4: {
        "formula": "IF(MEAN(CLOSE,8)+STD(CLOSE,8)<MEAN(CLOSE,2),-1,IF(MEAN(CLOSE,2)<MEAN(CLOSE,8)-STD(CLOSE,8),1,IF(VOLUME/MEAN(VOLUME,20)>=1,1,-1)))",
        "description": "均线、波动和成交量活跃度共同决定方向的离散因子。",
        "required_fields": ["close", "volume"],
        "parameters": {"price_window": 8, "short_window": 2, "volume_window": 20},
    },
    5: {
        "formula": "(-1 * TSMAX(CORR(TSRANK(VOLUME,5), TSRANK(HIGH,5), 5), 3))",
        "description": "成交量与最高价时序排序相关性的短窗最大值反向因子。",
        "required_fields": ["high", "volume"],
        "parameters": {"rank_window": 5, "corr_window": 5, "max_window": 3},
    },
    6: {
        "formula": "(-1 * RANK(SIGN(DELTA(OPEN * 0.85 + HIGH * 0.15, 4))))",
        "description": "加权开高价四日变化方向的反向横截面排序。",
        "required_fields": ["open", "high"],
        "parameters": {"delta_window": 4},
    },
    7: {
        "formula": "((RANK(TSMAX(VWAP-CLOSE,3)) + RANK(TSMIN(VWAP-CLOSE,3))) * RANK(DELTA(VOLUME,3)))",
        "description": "VWAP 相对收盘价短窗极值与成交量变化排序的复合因子。",
        "required_fields": ["open", "high", "low", "close", "volume", "amount"],
        "parameters": {"extreme_window": 3, "delta_window": 3},
    },
    8: {
        "formula": "RANK(-1 * DELTA(((HIGH+LOW)/2*0.2 + VWAP*0.8), 4))",
        "description": "混合价格四日变化的反向横截面排序。",
        "required_fields": ["open", "high", "low", "close", "volume", "amount"],
        "parameters": {"delta_window": 4},
    },
    9: {
        "formula": "SMA(((HIGH+LOW)/2 - DELAY((HIGH+LOW)/2,1)) * (HIGH-LOW) / VOLUME, 7, 2)",
        "description": "价格中枢变化、振幅和成交量构造的国泰君安 SMA 平滑因子。",
        "required_fields": ["high", "low", "volume"],
        "parameters": {"sma_window": 7, "sma_weight": 2},
    },
    10: {
        "formula": "RANK(TSMAX(((RET < 0) ? STD(RET,20) : CLOSE)^2, 5))",
        "description": "下跌时使用收益波动率、否则使用收盘价平方，再做短窗最大值排序。",
        "required_fields": ["close"],
        "parameters": {"std_window": 20, "max_window": 5},
    },
}


def gtja191_specs() -> list[FactorResearchSpec]:
    specs: list[FactorResearchSpec] = []
    for idx in range(1, 11):
        details = GTJA191_IMPLEMENTED_DETAILS[idx]
        specs.append(
            FactorResearchSpec(
                factor_name=f"alpha{idx}",
                library="GTJA191",
                version=GTJA191_VERSION,
                display_name=f"GTJA191 Alpha#{idx}",
                factor_id=f"gtja191_alpha_{idx:03d}",
                source_document=GTJA191_SOURCE,
                formula=str(details["formula"]),
                description=str(details["description"]),
                required_fields=list(details["required_fields"]),
                parameters=dict(details["parameters"]),
                validation_targets=GTJA191_COMMON_THRESHOLDS,
                tags=["gtja191", "price_volume", "implemented"],
                metadata={"status": "implemented", "implementation_stage": "factor_lab"},
            )
        )
    return specs
