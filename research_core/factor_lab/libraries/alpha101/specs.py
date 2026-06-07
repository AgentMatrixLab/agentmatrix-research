from __future__ import annotations

from contracts.factor_research import FactorResearchSpec, ValidationThreshold


ALPHA101_SOURCE = "WorldQuant 101 Formulaic Alphas"
ALPHA101_VERSION = "v2026.06"
ALPHA101_COMMON_THRESHOLDS = [
    ValidationThreshold("formula_match_ratio", ">=", 1.0, "代码实现与规格书公式逐项一致。"),
    ValidationThreshold("field_mapping_match_ratio", ">=", 1.0, "字段、复权、频率和股票池口径一致。"),
    ValidationThreshold("sample_point_error_ratio", "<=", 0.0, "抽样点位误差为零。"),
    ValidationThreshold("cross_section_spearman", ">=", 0.99, "与外部真值做截面对齐。"),
]


ALPHA101_IMPLEMENTED_DETAILS: dict[int, dict[str, object]] = {
    1: {
        "formula": "(rank(Ts_ArgMax(SignedPower(((returns < 0) ? stddev(returns, 20) : close), 2.), 5)) - 0.5)",
        "description": "下跌时使用 20 日收益波动率、否则使用收盘价，再做 5 日 argmax 横截面排序。",
        "required_fields": ["close"],
        "parameters": {"std_window": 20, "argmax_window": 5},
        "notes": ["需要先计算 1 日 returns。", "输出为横截面 rank 后减 0.5。"],
    },
    2: {
        "formula": "(-1 * correlation(rank(delta(log(volume), 2)), rank(((close - open) / open)), 6))",
        "description": "成交量对数变化与日内收益率排序之间的 6 日滚动相关反向因子。",
        "required_fields": ["open", "close", "volume"],
        "parameters": {"delta_window": 2, "corr_window": 6},
        "notes": ["volume 先取 log 再做 2 日 delta。"],
    },
    3: {
        "formula": "(-1 * correlation(rank(open), rank(volume), 10))",
        "description": "开盘价排序与成交量排序的 10 日滚动相关反向因子。",
        "required_fields": ["open", "volume"],
        "parameters": {"corr_window": 10},
        "notes": ["先做横截面 rank，再做按证券维度滚动相关。"],
    },
    4: {
        "formula": "(-1 * Ts_Rank(rank(low), 9))",
        "description": "最低价横截面排序的 9 日时序排序反向因子。",
        "required_fields": ["low"],
        "parameters": {"ts_rank_window": 9},
        "notes": ["先做横截面 rank，再做时间序列 rank。"],
    },
    5: {
        "formula": "(rank((open - (sum(vwap, 10) / 10))) * (-1 * abs(rank((close - vwap)))))",
        "description": "开盘价相对 10 日均值 VWAP 偏离与收盘价相对当日 VWAP 偏离的组合因子。",
        "required_fields": ["open", "close", "high", "low", "volume", "amount"],
        "parameters": {"vwap_mean_window": 10},
        "notes": ["VWAP 采用 amount / volume，缺失时回退到 OHLC 均值。"],
    },
    6: {
        "formula": "(-1 * correlation(open, volume, 10))",
        "description": "开盘价与成交量的 10 日滚动相关反向因子。",
        "required_fields": ["open", "volume"],
        "parameters": {"corr_window": 10},
        "notes": ["按证券维度滚动相关。"],
    },
    7: {
        "formula": "((adv20 < volume) ? ((-1 * ts_rank(abs(delta(close, 7)), 60)) * sign(delta(close, 7))) : (-1 * 1))",
        "description": "成交量放大时使用 7 日价格变化幅度的 60 日时序排序，否则固定为 -1。",
        "required_fields": ["close", "volume", "amount"],
        "parameters": {"adv_window": 20, "delta_window": 7, "ts_rank_window": 60},
        "notes": ["adv20 这里以成交额 20 日均值近似。"],
    },
    8: {
        "formula": "(-1 * rank(((sum(open, 5) * sum(returns, 5)) - delay((sum(open, 5) * sum(returns, 5)), 10))))",
        "description": "5 日开盘价累计与 5 日收益累计乘积相对 10 日前的变化反向排序因子。",
        "required_fields": ["open", "close"],
        "parameters": {"sum_window": 5, "delay_window": 10},
        "notes": ["需要先计算 returns。"],
    },
    9: {
        "formula": "((0 < ts_min(delta(close, 1), 5)) ? delta(close, 1) : ((ts_max(delta(close, 1), 5) < 0) ? delta(close, 1) : (-1 * delta(close, 1))))",
        "description": "根据近 5 日价格变化方向一致性决定是否对 1 日价格变化取反。",
        "required_fields": ["close"],
        "parameters": {"delta_window": 1, "state_window": 5},
        "notes": ["这是时序条件分支因子，不做横截面排序。"],
    },
    10: {
        "formula": "rank(((0 < ts_min(delta(close, 1), 4)) ? delta(close, 1) : ((ts_max(delta(close, 1), 4) < 0) ? delta(close, 1) : (-1 * delta(close, 1)))))",
        "description": "Alpha10 在 Alpha9 的条件分支基础上增加横截面排序。",
        "required_fields": ["close"],
        "parameters": {"delta_window": 1, "state_window": 4},
        "notes": ["先构造 inner，再做横截面 rank。"],
    },
}


def alpha101_specs() -> list[FactorResearchSpec]:
    specs: list[FactorResearchSpec] = []
    for idx in range(1, 102):
        details = ALPHA101_IMPLEMENTED_DETAILS.get(idx, {})
        implemented = idx in ALPHA101_IMPLEMENTED_DETAILS
        specs.append(
            FactorResearchSpec(
                factor_name=f"alpha{idx}",
                library="Alpha101",
                version=ALPHA101_VERSION,
                display_name=f"Alpha101 #{idx}",
                factor_id=f"WQ101_{idx:03d}",
                source_document=ALPHA101_SOURCE,
                formula=str(details.get("formula", "")),
                description=str(details.get("description", "Alpha101 标准样板因子，后续将补齐公式、实现、真值与检验产物。")),
                frequency="day",
                sample_scope="A-share standard pool; remove ST, delisted, and newly listed securities when applicable.",
                required_fields=list(details.get("required_fields", ["open", "high", "low", "close", "volume", "amount"])),
                parameters=dict(details.get("parameters", {})),
                preprocessing=["adjust_prices", "align_trading_calendar", "winsorize_if_required"],
                neutralization=["industry", "size"],
                validation_targets=list(ALPHA101_COMMON_THRESHOLDS),
                tags=["alpha101", "worldquant", "formulaic-alpha"],
                notes=list(details.get("notes", [
                    "当前阶段先建立统一规格层和证明包模板。",
                    "具体公式将在接入官方附录或公开可核验参考实现后逐项补齐。",
                ])),
                metadata={
                    "status": "implemented" if implemented else "planned",
                    "implementation_stage": "code" if implemented else "spec",
                    "source_priority": "official_appendix_first",
                },
            )
        )
    return specs
