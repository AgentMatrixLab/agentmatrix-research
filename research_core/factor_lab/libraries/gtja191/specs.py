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
    11: {
        "formula": "SUM((((CLOSE - LOW) - (HIGH - CLOSE)) / (HIGH - LOW)) * VOLUME, 6)",
        "description": "收盘价在日内振幅中的相对位置乘以成交量，并做 6 日滚动求和。",
        "required_fields": ["high", "low", "close", "volume"],
        "parameters": {"sum_window": 6},
    },
    12: {
        "formula": "RANK(OPEN - SUM(VWAP,10) / 10) * (-1 * RANK(ABS(CLOSE - VWAP)))",
        "description": "开盘价相对 10 日 VWAP 均值偏离排序，并乘以收盘价偏离 VWAP 绝对值排序的负值。",
        "required_fields": ["open", "close", "volume", "amount"],
        "parameters": {"sum_window": 10},
    },
    13: {
        "formula": "((HIGH * LOW)^0.5 - VWAP)",
        "description": "最高价与最低价几何均值相对 VWAP 的偏离因子。",
        "required_fields": ["high", "low", "volume", "amount"],
        "parameters": {},
    },
    14: {
        "formula": "CLOSE - DELAY(CLOSE,5)",
        "description": "收盘价相对 5 日前收盘价的变化因子。",
        "required_fields": ["close"],
        "parameters": {"delay_window": 5},
    },
    15: {
        "formula": "OPEN / DELAY(CLOSE,1) - 1",
        "description": "开盘价相对前一日收盘价的隔夜收益因子。",
        "required_fields": ["open", "close"],
        "parameters": {"delay_window": 1},
    },
    16: {
        "formula": "(-1 * TSMAX(RANK(CORR(RANK(VOLUME), RANK(VWAP), 5)), 5))",
        "description": "成交量排序与 VWAP 排序相关性的短窗最大值反向因子。",
        "required_fields": ["volume", "amount"],
        "parameters": {"corr_window": 5, "max_window": 5},
    },
    17: {
        "formula": "RANK((VWAP - TSMAX(VWAP,15))^DELTA(CLOSE,5))",
        "description": "VWAP 相对 15 日最高 VWAP 的偏离与收盘价 5 日变化构造的排序因子。",
        "required_fields": ["close", "volume", "amount"],
        "parameters": {"max_window": 15, "delta_window": 5},
    },
    18: {
        "formula": "CLOSE / DELAY(CLOSE,5)",
        "description": "收盘价相对 5 日前收盘价的价格比值因子。",
        "required_fields": ["close"],
        "parameters": {"delay_window": 5},
    },
    19: {
        "formula": "IF(CLOSE < DELAY(CLOSE,5), (CLOSE - DELAY(CLOSE,5)) / DELAY(CLOSE,5), IF(CLOSE = DELAY(CLOSE,5), 0, (CLOSE - DELAY(CLOSE,5)) / CLOSE))",
        "description": "按收盘价相对 5 日前收盘价涨跌方向构造的条件收益因子。",
        "required_fields": ["close"],
        "parameters": {"delay_window": 5},
    },
    20: {
        "formula": "(CLOSE - DELAY(CLOSE,6)) / DELAY(CLOSE,6) * 100",
        "description": "收盘价相对 6 日前收盘价的百分比变化因子。",
        "required_fields": ["close"],
        "parameters": {"delay_window": 6},
    },
}


def gtja191_specs() -> list[FactorResearchSpec]:
    specs: list[FactorResearchSpec] = []
    for idx in range(1, 21):
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
