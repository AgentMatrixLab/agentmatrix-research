def compute_factor(panel):
    result = panel[["date", "symbol"]].copy()
    result["factor_value"] = panel["close"].pct_change().fillna(0.0)
    return result
