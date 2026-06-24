"""VM-side regression check — DEPRECATED, merged into check_regression.py Path B.

This file is kept for reference.  Use check_regression.py instead:
  python scripts/check_regression.py <GM_TOKEN>           # check
  python scripts/check_regression.py <GM_TOKEN> --generate  # regenerate

check_regression.py auto-detects GM SDK availability and routes to
Path B (real GM) or Path A (stub) automatically.
"""
import sys, os, json, csv
from pathlib import Path

TOKEN = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("GM_TOKEN", "")
if not TOKEN:
    print("ERROR: pass token as first argument")
    sys.exit(2)

GENERATE = "--generate" in sys.argv

PROJECT_DIR = Path("C:/Users/lorenzoteng/.goldminer3/projects")
BASELINE_DIR = PROJECT_DIR / "b8fe2688-60b9-11f1-a8be-001c42cd99e0"
BASELINE_FILE = BASELINE_DIR / "vm_regression_baseline.json"
THRESHOLD = 0.05

sys.path.insert(0, str(PROJECT_DIR))
from gm.api import set_token
set_token(TOKEN)
from gm_factor_lib import calc_factors

FACTORS = [
    "market_cap", "pe_ttm", "pb_ratio", "roe_ttm", "roa",
    "gross_profit_margin", "net_profit_margin",
    "momentum_120d", "momentum_252d", "volatility_120d",
    "total_assets_growth_rate", "net_profit_growth_per_share",
    "KDJ_K", "KDJ_D", "RSI",
    "net_operate_cash_flow", "bps",
]

STOCKS = [
    "SHSE.600519", "SHSE.600036", "SHSE.601318", "SHSE.600900", "SHSE.601166",
    "SHSE.600887", "SHSE.601398", "SHSE.600809", "SZSE.000858", "SZSE.000651",
    "SZSE.000333", "SZSE.002415", "SZSE.300750", "SZSE.000001", "SZSE.000568",
    "SHSE.601012", "SHSE.600276", "SHSE.601899", "SHSE.600585", "SHSE.601668",
]

def compute():
    result = calc_factors(
        securities=STOCKS, factors=FACTORS,
        start_date="2025-12-31", end_date="2025-12-31",
        use_real_price=True, skip_paused=True,
    )
    flat = {}
    for factor_name, df in result.items():
        vals = []
        for col in df.columns:
            v = df[col].iloc[0] if len(df) > 0 else None
            if v is not None and str(v) != "nan":
                vals.append(float(v))
        if vals:
            flat[factor_name] = {
                "count": len(vals),
                "mean": sum(vals) / len(vals),
                "values": sorted(vals),
            }
    return flat

current = compute()
print(f"Computed: {len(current)} factors")

if GENERATE:
    BASELINE_FILE.write_text(json.dumps(current, indent=2))
    print(f"Baseline saved: {BASELINE_FILE}")
    sys.exit(0)

if not BASELINE_FILE.exists():
    print("ERROR: no baseline. Run with --generate first.")
    sys.exit(2)

baseline = json.loads(BASELINE_FILE.read_text())
failures = 0

for fk, bl in baseline.items():
    cur = current.get(fk)
    if cur is None:
        print(f"  MISSING: {fk}")
        failures += 1
        continue
    count_change = abs(cur["count"] - bl["count"]) / max(bl["count"], 1)
    if count_change > THRESHOLD:
        print(f"  COUNT: {fk}: {bl['count']} -> {cur['count']} ({count_change:.1%})")
        failures += 1
        continue
    mean_change = abs(cur["mean"] - bl["mean"]) / max(abs(bl["mean"]), 1e-10)
    if mean_change > THRESHOLD:
        print(f"  MEAN:  {fk}: {bl['mean']:.4f} -> {cur['mean']:.4f} ({mean_change:.1%})")
        failures += 1
        continue

if failures == 0:
    print(f"PASSED: {len(baseline)} factors stable")
    sys.exit(0)
print(f"FAILED: {failures} regression(s)")
sys.exit(1)
