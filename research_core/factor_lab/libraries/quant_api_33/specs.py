from __future__ import annotations

from research_core.factor_lab.libraries.quant_api_33.factors import IMPLEMENTED_QUANT_API_33_FACTORS


SOURCE = "Quant API factor_monthly"
LIBRARY = "QuantAPI"

PRICE_FACTORS = {
    "ret_1m",
    "ret_3m",
    "ret_6m",
    "ret_12m",
    "reversal",
    "momentum_12_1",
    "log_price",
}

VOLUME_FACTORS = {
    "avg_amount_1m",
    "log_amount_1m",
    "turnover_proxy",
    "volume_ratio",
    "illiquidity",
}

TECHNICAL_FACTORS = {
    "volatility_1m",
    "volatility_3m",
    "volatility_6m",
    "max_ret_1m",
    "min_ret_1m",
    "up_ratio_1m",
    "ma_signal",
    "vol_convergence",
    "high_low_1m",
    "rsi_14",
    "bb_position",
    "ret_3m_vol_adj",
    "amplitude_1m",
}

FINANCIAL_FACTORS = {
    "roe_ttm",
    "roa_ttm",
    "net_margin",
    "debt_to_asset",
    "revenue_yoy",
    "profit_yoy",
    "eps_yoy",
    "asset_turnover",
}

REQUIRED_FIELDS = {
    "roe_ttm": ["net_profit_ttm", "equity"],
    "roa_ttm": ["net_profit_ttm", "assets"],
    "net_margin": ["net_profit_ttm", "revenue_ttm"],
    "debt_to_asset": ["liabilities", "assets"],
    "revenue_yoy": ["revenue_yoy"],
    "profit_yoy": ["profit_yoy"],
    "eps_yoy": ["eps_yoy"],
    "asset_turnover": ["revenue_ttm", "assets"],
}

FORMULAS = {
    "ret_1m": "close / delay(close, 21) - 1",
    "ret_3m": "close / delay(close, 63) - 1",
    "ret_6m": "close / delay(close, 126) - 1",
    "ret_12m": "close / delay(close, 252) - 1",
    "volatility_1m": "stddev(daily_return, 21)",
    "volatility_3m": "stddev(daily_return, 63)",
    "reversal": "-ret_1m",
    "momentum_12_1": "delay(close, 21) / delay(close, 252) - 1",
    "avg_amount_1m": "mean(amount, 21)",
    "log_amount_1m": "log(avg_amount_1m)",
    "max_ret_1m": "max(daily_return, 21)",
    "min_ret_1m": "min(daily_return, 21)",
    "up_ratio_1m": "mean(daily_return > 0, 21)",
    "ma_signal": "close / mean(close, 20) - 1",
    "vol_convergence": "volatility_1m / volatility_3m",
    "illiquidity": "mean(abs(daily_return) / amount, 21)",
    "log_price": "log(close)",
    "turnover_proxy": "volume / mean(volume, 252)",
    "volatility_6m": "stddev(daily_return, 126)",
    "volume_ratio": "mean(volume, 5) / mean(volume, 21)",
    "high_low_1m": "max(high, 21) / min(low, 21) - 1",
    "rsi_14": "100 - 100 / (1 + mean(up_move, 14) / mean(down_move, 14))",
    "bb_position": "(close - bollinger_lower_20_2) / (bollinger_upper_20_2 - bollinger_lower_20_2)",
    "ret_3m_vol_adj": "ret_3m / volatility_3m",
    "amplitude_1m": "mean((high - low) / close, 21)",
    "roe_ttm": "net_profit_ttm / equity",
    "roa_ttm": "net_profit_ttm / assets",
    "net_margin": "net_profit_ttm / revenue_ttm",
    "debt_to_asset": "liabilities / assets",
    "revenue_yoy": "revenue_yoy",
    "profit_yoy": "profit_yoy",
    "eps_yoy": "eps_yoy",
    "asset_turnover": "revenue_ttm / assets",
}


def quant_api_33_specs() -> list[dict[str, object]]:
    return [_spec(name) for name in IMPLEMENTED_QUANT_API_33_FACTORS]


def _spec(name: str) -> dict[str, object]:
    if name in FINANCIAL_FACTORS:
        category = "财务因子"
        subcategory = "盈利能力"
        required_fields = REQUIRED_FIELDS[name]
    elif name in TECHNICAL_FACTORS:
        category = "技术因子"
        subcategory = "价量相关"
        required_fields = ["open", "high", "low", "close", "volume", "amount"]
    elif name in VOLUME_FACTORS:
        category = "量价因子"
        subcategory = "流动性"
        required_fields = ["close", "volume", "amount"]
    else:
        category = "量价因子"
        subcategory = "动量"
        required_fields = ["close"]

    return {
        "factor_name": name,
        "factor_id": f"QuantAPI:{name}",
        "display_name": name,
        "library": LIBRARY,
        "required_fields": required_fields,
        "formula": FORMULAS[name],
        "description": f"Independent local reproduction of Quant API factor_monthly factor {name}.",
        "source_document": SOURCE,
        "tags": ["quant-api-33", "factor-monthly", category],
        "category": category,
        "subcategory": subcategory,
        "status": "implemented",
        "metadata": {
            "official_factor_name": name,
            "official_source": SOURCE,
            "category": category,
            "subcategory": subcategory,
        },
    }
