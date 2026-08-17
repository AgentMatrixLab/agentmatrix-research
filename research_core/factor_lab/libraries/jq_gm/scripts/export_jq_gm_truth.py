#!/usr/bin/env python3
"""Export jq_gm factor truth values via GM SDK.

Requires GM terminal. Falls back gracefully when unavailable.
"""
import sys, os, json
import pandas as pd

# GM SDK project dir (gm_factor_lib.py lives here), set via env var
_PROJECT_DIR = os.environ.get("GM_PROJECT_DIR", "")
if _PROJECT_DIR and os.path.isdir(_PROJECT_DIR):
    sys.path.insert(0, _PROJECT_DIR)

try:
    from gm_factor_lib import calc_factors
    _GM_AVAILABLE = True
except ImportError:
    _GM_AVAILABLE = False

FACTORS = [
    "market_cap", "circulating_market_cap", "pe_ttm", "pe_ratio",
    "pb_mrq", "pb_ratio", "ps_ttm", "pcf_ttm",
    "roe_ttm", "roe_weighted", "roa_ttm", "roa_weighted",
    "gross_profit_margin_ttm", "net_profit_margin_ttm",
    "operating_revenue_growth_rate", "operating_revenue_ttm",
    "net_profit_growth_rate", "net_profit_ttm",
    "total_asset_turnover_ratio", "current_ratio",
    "quick_ratio", "debt_to_asset_ratio",
    "dividend_yield_ratio", "eps_ttm",
    "turnover_ratio", "volume_ratio",
    "momentum_20d", "momentum_60d",
]

if not _GM_AVAILABLE:
    print("gm_factor_lib not available (GM terminal required)")
    sys.exit(0)

def main():
    token = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("GM_TOKEN", "")
    if not token:
        print("Usage: python export_jq_gm_truth.py <GM_TOKEN>")
        sys.exit(1)
    
    from gm.api import set_token
    set_token(token)
    
    securities = ["SHSE.600519", "SZSE.000858", "SHSE.600036", "SZSE.000001", "SHSE.601318"]
    result = calc_factors(
        securities=securities,
        factors=FACTORS,
        start_date="2024-01-02",
        end_date="2024-01-10",
        use_real_price=True,
    )
    print(json.dumps({"status": "ok", "factors": len(FACTORS), "dates": len(result)}, indent=2))

if __name__ == "__main__":
    main()
