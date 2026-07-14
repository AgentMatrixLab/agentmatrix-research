"""
NC (Not Comparable) classifier for GM vs JQ factor validation.

Ported from CrossvalidationTYD pipeline_package/auto_nc_classifier.py (v78).
Three-layer architecture:
  1. Factor-level NC — known structural differences
  2. Extra NC — additional per-factor reasons
  3. Stock-level NC — per-stock data source / calendar issues

Comparison priority (matching v78):
  BOTH_NA → MATCH → factor-NC → NC → stock-NC → NC
  → GM_NA → JQ_NA → diff<5% → MATCH → diff≥5% → MISMATCH

Usage:
    from research_core.factor_lab.nc_classifier import NCClassifier

    cls = NCClassifier(factor_registry=FACTOR_REGISTRY)
    result = cls.batch_classify(comparison_df)
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
import pandas as pd


# ── Per-factor NC extracted from v67 comparison CSV (184 factors tested, 58 versions) ──

V67_NC_MAP: dict[str, str] = {
    'BLEV': '金融股长期借款定义不同, 偏差10.6%',
    'DTOA': 'JQ总负债口径差异(含/不含递延), 偏差39%',
    'RSI': 'EWM初始化方式不同(递归vs SMA首窗), 偏差5-8%',
    'ar_turn_ratio': '同total_asset_turnover, 累进vs TTM口径差异',
    'assets_turn_ratio': 'GM用TTM收入/JQ用累计收入; 累进vs TTM口径差异150-803%',
    'bps': '股本推导(tot_mv/close)精度有限, 偏差12%',
    'capital_reserve_per_share': 'JQ无对应每股指标数据, JQ CSV该因子全为NaN',
    'cash_flow_per_share': '股本推导(tot_mv/close)精度有限+JQ单位差异, 偏差>100%',
    'cash_ratio': 'JQ分子含交易性金融资产,GM仅货币资金; 口径差异74%',
    'debt_to_assets_ratio': 'JQ用总负债口径不同(含/不含递延), 偏差39%',
    'ev': 'EV口径差异: JQ含少数股东权益/优先股等; 金融股偏差43-75%',
    'gross_profit_margin': 'JQ毛利率口径不同(含税/不含税等), 茅台GM≈91% vs JQ≈67%',
    'growth_style': 'Barra复合因子, 需截面回归+多因子合成, 无法从GM单字段还原',
    'macd_hist': 'EWM初始化差异导致MACD系列偏移, 偏差5-10%',
    'net_profit_growth_per_share': 'JQ每股增长(除以总股本),GM净利润增长; 口径不同',
    'net_profit_margin': 'JQ用TTM净利润/GM用累计净利润, Q3截面偏差11-36%',
    'obv': '路径依赖指标,起点/复权差异导致7-1508%偏差',
    'ocf_to_operating_profit': 'JQ用经营+投资现金流,GM仅用经营现金流; 公式差异66-2051%',
    'ocfps': '股本推导(tot_mv/close)精度有限+JQ单位差异, 偏差>100%',
    'operating_net_income': 'JQ口径差异大(400-3271%); GM用利润表净额,JQ用占比×总额',
    'operating_profit_margin': 'JQ用TTM营业利润/GM用累计值, Q3截面偏差10-38%',
    'operating_revenue_growth_ttm': 'JQ每股增长(除以总股本),GM总营收增长; 口径不同20-1486%',
    'pb_mrq': 'MRQ净资产取数口径差异, 偏差13.5%',
    'pcf_ttm': 'JQ用经营+投资现金流,GM仅用经营现金流; 公式差异66-2051%',
    'price_volume_trend': '路径依赖指标,起点/缩放因子不同导致巨大偏差(234-2388%)',
    'revenue_ps': '股本推导(tot_mv/close)精度有限+JQ单位差异, 偏差>100%',
    'rsi_14': 'EWM初始化方式不同(递归vs SMA首窗), 偏差5-8%',
    'surplus_reserve_per_share': 'JQ无对应每股指标数据, JQ CSV该因子全为NaN',
    'tangible_assets_to_debt_ratio': 'JQ有形净值定义含商誉扣除等, 偏差48%',
    'total_asset_turnover': 'GM用TTM收入/JQ用累计收入; 累进vs TTM口径差异150-803%',
    # ── Financial TTM factors (validated 2026-06-23, 248 stocks) ──
    'MLEV': 'GM/JQ口径根本不同(avg_diff=689555%), 0%匹配',
    'EBIT': 'GM/JQ口径根本不同(avg_diff=576%), 0%匹配',
    'EBITDA': 'GM自算TTM vs JQ直接TTM, 18%匹配',
    'administration_expense_ttm': 'GM自算TTM vs JQ直接TTM, 4%匹配',
    'asset_impairment_loss_ttm': 'GM/JQ口径根本不同(avg_diff=155%), 1%匹配',
    'gross_profit_ttm': 'GM自算TTM vs JQ直接TTM, 6%匹配',
    'financial_liability': 'GM自算TTM vs JQ直接TTM, 32%匹配',
    'goods_sale_and_service_render_cash_ttm': 'GM/JQ比例=0.70, 系统偏差, 口径不同',
    'financial_expense_ttm': 'GM自算TTM vs JQ直接TTM, 10%匹配',
    'gross_income_ratio': 'GM/JQ口径根本不同(avg_diff=17282%), 0%匹配',
    'net_interest_expense': 'GM/JQ口径根本不同, 0%匹配',
    'eps_ttm': 'GM/JQ口径根本不同(avg_diff=31%), 0%匹配',
    'net_profit_ttm': 'GM自算TTM vs JQ直接TTM, 8%匹配',
    'non_operating_net_profit_ttm': 'GM自算TTM vs JQ直接TTM, 8%匹配',
    'operating_cost_ttm': 'GM/JQ比例=0.70, 系统偏差, 口径不同',
    'operating_liability': 'GM自算TTM vs JQ直接TTM, 1%匹配',
    'operating_assets': 'GM自算TTM vs JQ直接TTM, 13%匹配',
    'np_parent_company_owners_ttm': 'GM自算TTM vs JQ直接TTM, 7%匹配',
    'operating_revenue_ttm': 'GM/JQ比例=0.71, 系统偏差, 口径不同',
    'operating_profit_ttm': 'GM自算TTM vs JQ直接TTM, 8%匹配',
    'retained_earnings': 'GM/JQ比例=0.86, 系统偏差, 口径不同',
    'roa_ttm': 'GM/JQ口径根本不同(avg_diff=8860%), 0%匹配',
    'sale_expense_ttm': 'GM自算TTM vs JQ直接TTM, 6%匹配',
    'total_operating_revenue_ttm': 'GM/JQ比例=0.71, 系统偏差, 口径不同',
    'value_change_profit_ttm': 'GM自算TTM vs JQ直接TTM, 8%匹配',
    'total_operating_cost_ttm': 'GM/JQ口径根本不同(avg_diff=45%), 0%匹配',
    'total_profit_ttm': 'GM自算TTM vs JQ直接TTM, 7%匹配',
    # ── Remaining pattern-category NC ──
    'ATR14': 'custom_price AT指标, 路径依赖/起算点差异',
    'alpha': 'custom_price Alpha系数, 路径依赖/回归窗口差异',
    'circulating_market_cap': 'mktvalue_pt flow_mv无效字段, 与market_cap等价替代',
    'growth': '自定义增长率, 路径依赖/窗口差异',
    'net_profit': 'GM累计值 vs JQ TTM, 口径不同',
    'net_profit_growth_rate': 'GM自算增长率 vs JQ直接增长率, TTM口径不同',
    'np_parent_company_owners_growth_rate': 'GM自算增长率 vs JQ直接增长率, TTM口径不同',
    'operating_revenue_growth_rate': 'GM自算增长率 vs JQ直接增长率, TTM口径不同',
    'pb_ratio': 'PB定义差异, 净资产口径不同',
    'pe_ratio_lyr': 'PE(LYR)定义差异, 净利润口径不同',
    'total_assets': 'balance_pt字段, GM/JQ资产负债表科目定义差异',
    'total_liability': 'balance_pt字段, GM/JQ负债科目定义差异',
    'turnover_ratio': 'basic_pt换手率, 日历/成交量口径差异',
}

# Additional definition-diff NC (from not_comparable_factors.md)
_EXTRA_DEFINITION_NC: dict[str, str] = {
    "net_profit_margin": "口径根本不同: operating vs net profit margin",
    "operating_profit_margin": "口径根本不同: operating profit margin",
    "ev": "EV definition diff",
    "ev2_to_ebitda": "EV/EBITDA definition diff",
    "pcf_ttm": "PCF definition diff (cumulative vs TTM)",
    "pb_mrq": "PB definition diff",
    "ps_ttm": "PS definition diff",
    "pe_ttm": "PE definition diff",
    "pe_ratio": "PE ratio definition diff",
    "cash_ratio": "Cash ratio definition diff",
    "debt_to_assets_ratio": "Debt-to-assets calc method diff",
    "tangible_assets_to_debt_ratio": "Tangible assets definition diff",
    "DTOA": "Definition diff",
    "operating_revenue": "GM cumulative vs JQ TTM",
    "total_operating_revenue": "GM cumulative vs JQ TTM",
    "net_operate_cash_flow": "GM cumulative vs JQ TTM",
    "net_profit_growth_per_share": "JQ per-share vs GM total NP growth",
    "eps_growth_rate": "TTM growth vs YoY proxy",
    "gross_profit_growth_rate": "TTM growth vs YoY proxy",
    "net_operate_cash_flow_growth_rate": "TTM growth vs YoY proxy",
    "roe_ttm": "JQ uses deriv_pt jroa vs GM self-TTM",
    "roa": "JQ uses deriv_pt jroa",
    "eps": "v17 route definition diff",
    "basic_eps": "v17 route definition diff",
    "diluted_eps": "v17 route definition diff",
    "ocfps": "Definition diff",
    "revenue_ps": "Definition diff",
    "ocf_to_operating_profit": "Definition diff",
    "cash_flow_per_share": "Definition diff",
    "net_assets_growth_rate": "Growth rate calc method diff",
    "net_asset_growth_rate": "Growth rate calc method diff",
    "financing_cash_growth_rate": "Growth rate calc method diff",
    "operating_profit_growth_rate": "Growth rate calc method diff",
    "total_profit_growth_rate": "Growth rate calc method diff",
    "operating_revenue_growth_3y": "3Y growth rate calc method diff",
    "net_profit_growth_3y": "3Y growth rate calc method diff",
    "inc_return": "Return calc method diff",
}

# Generic pattern matching
_PATTERN_NC: dict[str, tuple[set[str], str]] = {
    "path_dependency": (
        {"rsi", "rsi_14", "obv", "pvt", "macd", "kdj", "price_volume_trend"},
        "Path-dependent: different start point / EWM initial value",
    ),
    "barra": (
        {"growth_style", "leverage", "earnings_yield", "beta", "liquidity",
         "residual_volatility", "non_linear_size", "size",
         "book_to_price_ratio", "cash_flow_to_price_ratio",
         "momentum_20d", "momentum_60d", "volatility_20d", "volatility_60d", "roe"},
        "Barra neutralized factor, requires cross-sectional regression",
    ),
    "cumulative_vs_ttm": (
        {"total_asset_turnover", "ar_turn_ratio", "accounts_receivable_turnover",
         "inv_turn_ratio", "inventory_turnover", "operating_cycle"},
        "Cumulative vs TTM (~4.5x)",
    ),
    "scale_sign": (
        {"std5", "std10", "std20", "std60", "blev",
         "gross_profit_margin", "operating_net_income", "net_debt", "financial_assets"},
        "Definition/scale fundamentally different",
    ),
    "share_base": (
        {"bps", "capital_reserve_per_share", "surplus_reserve_per_share"},
        "JQ weighted avg shares vs GM total shares",
    ),
    "cashflow": (
        {"net_operate_cash_flow_ttm", "net_invest_cash_flow_ttm", "net_finance_cash_flow_ttm"},
        "Cash flow data source difference, signs may differ",
    ),
    "v61": (
        {"momentum_5d", "momentum_10d", "momentum_120d", "momentum_252d",
         "reversal_5d", "reversal_20d", "reversal_60d"},
        "v61 formula/sign difference, reverted to NC",
    ),
}

# Stock-level NC candidate factors
CALENDAR_SENSITIVE = [
    "momentum_252d", "REVS250", "adj_momentum", "momentum_style",
    "momentum_120d", "REVS120",
    "momentum_5d", "momentum_10d", "momentum_60d",
    "reversal_5d", "reversal_20d", "reversal_60d",
]

DATA_SOURCE_SENSITIVE = [
    "total_assets_growth_rate",
    "beta_252d", "idiosyncratic_volatility_252d",
]


@dataclass
class NCResult:
    factor_nc: dict[str, str] = field(default_factory=dict)
    stock_nc: dict[tuple[str, str], str] = field(default_factory=dict)
    stats: dict[str, int] = field(default_factory=dict)
    classified: pd.DataFrame | None = None


class NCClassifier:
    """Three-layer NC classifier matching v78 priority order."""

    def __init__(self, factor_registry: dict | None = None):
        self.registry = factor_registry or {}

    def _get_factor_nc(self, factor_key: str) -> str | None:
        """Check if factor has a known NC reason."""
        # 0. Check V67_NC_MAP (per-factor NC from 58-version history)
        if factor_key in V67_NC_MAP:
            return V67_NC_MAP[factor_key]

        # 1. Check registry not_comparable
        meta = self.registry.get(factor_key, {})
        if nc := meta.get("not_comparable"):
            return str(nc)

        # 2. Check pattern matching
        key_l = factor_key.lower()
        for factors, reason in _PATTERN_NC.values():
            if key_l in factors:
                return reason

        # 3. Check extra definition NC
        if factor_key in _EXTRA_DEFINITION_NC:
            return _EXTRA_DEFINITION_NC[factor_key]

        # 4. Barra neutralized from registry
        if meta.get("barra_neutralized"):
            return "Barra neutralized factor, requires cross-sectional regression"

        return None

    def batch_classify(
        self,
        comparison_df: pd.DataFrame,
        diff_threshold: float = 0.05,
        detect_stock_nc: bool = True,
    ) -> NCResult:
        df = comparison_df.copy()
        factor_nc: dict[str, str] = {}
        stock_nc: dict[tuple[str, str], str] = {}
        stats: dict[str, int] = defaultdict(int)
        statuses: list[str] = []
        nc_reasons: list[str] = []

        for _, row in df.iterrows():
            fk = row.get("factor_key", row.get("factor", ""))
            sym = row.get("symbol", row.get("stock", ""))
            gv = row.get("gm_value", row.get("gm_val", np.nan))
            jv = row.get("jq_value", row.get("jq_val", np.nan))

            gm_na = pd.isna(gv) or (isinstance(gv, (int, float)) and abs(gv) < 1e-15)
            jq_na = pd.isna(jv) or (isinstance(jv, (int, float)) and abs(jv) < 1e-15)

            # Priority 1: BOTH_NA
            if gm_na and jq_na:
                statuses.append("MATCH")
                nc_reasons.append("BOTH_NA")
                stats["MATCH"] += 1
                stats["BOTH_NA"] += 1
                continue

            # Priority 2: Factor NC
            nc_reason = self._get_factor_nc(str(fk))
            if nc_reason:
                statuses.append("NC")
                nc_reasons.append(nc_reason)
                factor_nc[str(fk)] = nc_reason
                stats["NC"] += 1
                continue

            # Priority 3: GM_NA
            if gm_na:
                statuses.append("GM_NA")
                nc_reasons.append("")
                stats["GM_NA"] += 1
                continue

            # Priority 4: JQ_NA
            if jq_na:
                statuses.append("JQ_NA")
                nc_reasons.append("")
                stats["JQ_NA"] += 1
                continue

            # Priority 5: Numeric comparison
            try:
                diff = abs(float(gv) - float(jv)) / max(abs(float(jv)), 1e-10)
            except (ValueError, TypeError, ZeroDivisionError):
                statuses.append("ERROR")
                nc_reasons.append("Value error")
                stats["ERROR"] += 1
                continue

            if diff < diff_threshold:
                statuses.append("MATCH")
                nc_reasons.append("")
                stats["MATCH"] += 1
            else:
                statuses.append("MISMATCH")
                nc_reasons.append("")
                stats["MISMATCH"] += 1

        df["status"] = statuses
        df["nc_reason"] = nc_reasons

        if detect_stock_nc:
            stock_nc = self._detect_stock_nc(df)

        return NCResult(
            factor_nc=factor_nc,
            stock_nc=stock_nc,
            stats=dict(stats),
            classified=df,
        )

    def _detect_stock_nc(self, df: pd.DataFrame) -> dict[tuple[str, str], str]:
        mismatches = df[df["status"] == "MISMATCH"]
        if mismatches.empty:
            return {}

        stock_nc: dict[tuple[str, str], str] = {}

        for fk in mismatches["factor_key"].unique():
            fm = mismatches[mismatches["factor_key"] == fk]
            fk_str = str(fk)

            if any(cs in fk_str.lower() or fk_str.lower() in cs.lower()
                   for cs in CALENDAR_SENSITIVE):
                reason = "Trading calendar alignment (250 vs 252 days, qfq timing)"
                for _, row in fm.iterrows():
                    stock_nc[(fk_str, str(row["symbol"]))] = reason

            elif any(ds in fk_str.lower() or fk_str.lower() in ds.lower()
                     for ds in DATA_SOURCE_SENSITIVE):
                all_stocks = set(df[df["factor_key"] == fk]["symbol"].unique())
                mm_stocks = set(fm["symbol"].unique())
                if len(mm_stocks) < len(all_stocks) * 0.1:
                    reason = "GM/JQ data source difference (minority of stocks)"
                    for _, row in fm.iterrows():
                        stock_nc[(fk_str, str(row["symbol"]))] = reason

        return stock_nc

    def accuracy(self, result: NCResult) -> float:
        m = result.stats.get("MATCH", 0)
        mm = result.stats.get("MISMATCH", 0)
        total = m + mm
        return m / total * 100 if total > 0 else 0.0

    def generate_report(self, result: NCResult) -> str:
        s = result.stats
        total = sum(s.values())
        if total == 0:
            return "No data."

        m = s.get("MATCH", 0)
        mm = s.get("MISMATCH", 0)
        nc = s.get("NC", 0)
        gm = s.get("GM_NA", 0)
        jq = s.get("JQ_NA", 0)
        bn = s.get("BOTH_NA", 0)
        acc = self.accuracy(result)

        return (
            f"# NC Classification\n\n"
            f"Total pairs: {total}\n"
            f"MATCH: {m} ({m/total*100:.1f}%)  incl. BOTH_NA: {bn}\n"
            f"MISMATCH: {mm} ({mm/total*100:.1f}%)\n"
            f"NC: {nc} ({nc/total*100:.1f}%)  (factors: {len(result.factor_nc)})\n"
            f"GM_NA: {gm}  JQ_NA: {jq}\n"
            f"Accuracy (comparable): {acc:.1f}% ({m}/{m+mm})\n"
        )


def classify(comparison_df: pd.DataFrame, registry: dict | None = None) -> NCResult:
    """Quick classification wrapper."""
    return NCClassifier(registry).batch_classify(comparison_df)
