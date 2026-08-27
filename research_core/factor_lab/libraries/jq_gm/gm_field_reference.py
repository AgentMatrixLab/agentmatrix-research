"""GM API field reference for LLM factor generation.

Maps human-readable financial concepts to GM SDK API field names.
Include this in the LLM prompt when generating fundamental factors.
"""

GM_FIELD_REFERENCE = {
    # 市值与价格
    "总市值": "tot_mv",
    "流通市值": "negotiable_mv",
    "收盘价": "close",

    # 估值
    "市盈率(TTM)": "pe_ttm",
    "市盈率(LYR)": "pe_lyr",
    "市净率": "pb",
    "市净率(MRQ)": "pb_mrq",
    "市销率": "ps",
    "市销率(TTM)": "ps_ttm",
    "市现率": "pcf",
    "市现率(TTM)": "pcf_ttm",
    "企业价值": "ev",
    "EV/EBITDA": "ev2_to_ebitda",
    "股息率": "dividend_ratio",

    # 盈利能力
    "净资产收益率(TTM)": "roe_ttm",
    "总资产收益率(TTM)": "roa_ttm",
    "毛利率(TTM)": "gross_profit_margin",
    "净利率(TTM)": "net_profit_margin",
    "营业收入(TTM)": "operating_revenue_ttm",
    "营业利润(TTM)": "net_profit_ttm",  # 净利润
    "净利润": "net_profit",
    "EBIT(TTM)": "EBIT",
    "EBITDA(TTM)": "EBITDA",

    # 每股指标
    "每股收益": "eps",
    "基本每股收益": "basic_eps",
    "稀释每股收益": "diluted_eps",
    "每股净资产": "bps",
    "每股经营现金流": "ocfps",
    "每股营收": "revenue_ps",

    # 资产负债
    "总资产": "total_assets",
    "净资产": "total_owner_equities",
    "总负债": "total_liability",
    "净营运资本": "net_working_capital",
    "资产负债率": "DT...",

    # 现金流
    "经营活动现金流": "net_operate_cash_flow",
    "经营活动现金流(TTM)": "net_operate_cash_flow_ttm",
    "筹资活动现金流": "financing_cash",

    # 成长性
    "净利润增长率": "net_profit_growth_per_share",
    "营收增长率": "sales_growth",
    "总资产增长率": "total_assets_growth_rate",
    "净资产增长率": "net_asset_growth_rate",

    # 营运能力
    "总资产周转率": "assets_turn_ratio",
    "存货周转率": "inv_turn_ratio",
    "应收账款周转率": "ar_turn_ratio",
    "营业周期": "operating_cycle",

    # 动量
    "动量(1月)": "momentum_20d",
    "动量(3月)": "momentum_60d",
    "动量(6月)": "momentum_120d",
    "动量(12月)": "momentum_252d",
    "反转(5日)": "reversal_5d",
    "反转(20日)": "reversal_20d",
    "波动率(1月)": "volatility_20d",
    "波动率(3月)": "volatility_60d",
    "波动率(12月)": "volatility_252d",
    "贝塔(252日)": "beta_252d",
    "特质波动率(252日)": "idiosyncratic_volatility_252d",
    "夏普比率": "sharpe_ratio",
    "最大回撤(20日)": "max_drawdown_20d",
}

# GM-specific fields (exclude generic OHLCV names like close, volume)
_GM_SPECIFIC_FIELDS: set[str] = {
    v for k, v in GM_FIELD_REFERENCE.items()
    if v not in ("close", "open", "high", "low", "volume", "vwap")
}
GM_FIELD_NAMES = _GM_SPECIFIC_FIELDS
