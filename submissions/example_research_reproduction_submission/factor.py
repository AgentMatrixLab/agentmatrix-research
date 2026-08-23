def compute(panel):
    close = panel.sort_values(["code", "date"]).groupby("code")["close"]
    return close.pct_change().fillna(0.0).reindex(panel.sort_values(["code", "date"]).index).sort_index()
