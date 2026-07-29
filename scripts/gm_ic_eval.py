"""GM SDK IC evaluation for fundamental factors using GM SDK.

Usage: python gm_ic_eval.py <TOKEN> <factor_name>
Computes factor via GM SDK, evaluates IC against price returns.
"""
import sys, numpy as np, pandas as pd

PROJECT_DIR = "C:/Users/lorenzoteng/.goldminer3/projects"
sys.path.insert(0, PROJECT_DIR)

STOCKS = [
    "SHSE.600519","SHSE.600036","SHSE.601318","SHSE.600900","SHSE.601166",
    "SHSE.600887","SHSE.601398","SHSE.600809","SZSE.000858","SZSE.000651",
    "SZSE.000333","SZSE.002415","SZSE.300750","SZSE.000001","SZSE.000568",
]


def evaluate(token, factor_name, start="2020-01-01", end="2024-12-31"):
    from gm.api import set_token, history
    set_token(token)
    from gm_factor_lib import calc_factors

    result = calc_factors(securities=STOCKS, factors=[factor_name],
                          start_date=start, end_date=end,
                          use_real_price=True, skip_paused=True)
    df = result.get(factor_name, pd.DataFrame())
    if df.empty:
        return None

    stacked = df.stack(future_stack=True).reset_index()
    stacked.columns = ["date", "stock", "value"]
    stacked["value"] = pd.to_numeric(stacked["value"], errors="coerce")
    stacked = stacked.dropna()

    rets = []
    for s in STOCKS[:5]:
        try:
            h = history(s, frequency="1d", start_time=start, end_time=end,
                       fields="close", adjust=2, df=True)
            if h.empty: continue
            h = h.reset_index(); h.columns = ["date","close"]; h["stock"] = s
            h["fwd_ret"] = h.groupby("stock")["close"].pct_change(5).shift(-5)
            rets.append(h[["date","stock","fwd_ret"]])
        except Exception:
            pass

    if not rets:
        return None

    returns = pd.concat(rets, ignore_index=True)
    merged = stacked.merge(returns, on=["date","stock"], how="inner")
    ic_vals = []
    for dt, daily in merged.groupby("date"):
        valid = daily[["value","fwd_ret"]].dropna()
        if len(valid) < 5: continue
        c = valid["value"].corr(valid["fwd_ret"])
        if pd.notna(c): ic_vals.append(c)

    if not ic_vals: return None
    ic_mean = float(np.mean(ic_vals))
    ic_std = float(np.std(ic_vals, ddof=0))
    return {"factor": factor_name, "ic_mean": ic_mean, "icir": ic_mean/ic_std if ic_std>0 else 0, "samples": len(ic_vals)}


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python gm_ic_eval.py <TOKEN> <factor_name>")
        sys.exit(1)
    token = sys.argv[1]
    r = evaluate(token, sys.argv[2])
    if r:
        print(f"IC: {r['ic_mean']:+.4f}, ICIR: {r['icir']:+.3f}, n={r['samples']}")
