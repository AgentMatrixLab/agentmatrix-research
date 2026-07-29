"""
export_jq_gm_truth.py — 在 GM 掘金终端里直接运行。

放到 GM 项目目录下 (和 gm_factor_lib.py 同级), 然后:
    python export_jq_gm_truth.py

产出: jq_gm_truth.csv (宽格式, AgentMatrix proof-batch 直接用)
"""

import pandas as pd
from gm_factor_lib import calc_factors

# ── 31 个在 v78 达到 MISMATCH=0 的因子 ──

FACTORS = [
    # 基础科目及衍生类 (12)
    "market_cap", "circulating_market_cap", "pe_ttm", "pe_ratio",
    "pb_mrq", "ps_ttm", "pcf_ttm", "turnover_ratio",
    "total_operating_revenue_ttm", "operating_profit_ttm",
    "net_profit_ttm", "net_operate_cash_flow_ttm",
    # 质量类 (3)
    "roe_ttm", "net_profit_margin", "roa",
    # 动量类 (3)
    "momentum_20d", "momentum_60d", "REVS20",
    # 成长类 (3)
    "operating_revenue_growth_rate",
    "total_asset_growth_rate",
    "net_profit_growth_rate",
    # 技术指标 (4)
    "RSI", "MA5", "MA20", "MA60",
    # 情绪类 (3)
    "VOL20", "VR", "Variance20",
    # 基础扩展 (2)
    "net_working_capital", "retained_earnings",
    # 补充 (1)
    "total_asset_turnover",
]

# ── 股票池 ──

# 优先从 hs300.csv 读, 没有则用默认几只
try:
    stocks_df = pd.read_csv("hs300.csv")
    STOCKS = stocks_df.iloc[:, 0].tolist()
    print(f"Loaded {len(STOCKS)} stocks from hs300.csv")
except FileNotFoundError:
    STOCKS = [
        "SHSE.600519", "SZSE.000001", "SHSE.601318",
        "SZSE.000858", "SHSE.600036", "SHSE.600900",
        "SHSE.601166", "SZSE.002415",
    ]
    print(f"WARNING: hs300.csv not found, using {len(STOCKS)} demo stocks")

# ── 计算 ──

print(f"Computing {len(FACTORS)} factors for {len(STOCKS)} stocks...")
print(f"Date: 2026-03-17")

result = calc_factors(
    securities=STOCKS,
    factors=FACTORS,
    start_date="2026-03-17",
    end_date="2026-03-17",
    use_real_price=True,
    skip_paused=True,
)

# ── 转宽格式 ──
# result 格式: {factor_name: DataFrame(index=trade_date, columns=symbols)}
# 目标格式:    date, code, factor_1, factor_2, ...

frames = []
for name, df in result.items():
    if df.empty:
        print(f"  WARNING: {name} returned empty")
        continue
    # stack: (date, symbol) -> value
    s = df.stack(future_stack=True).reset_index()
    s.columns = ["date", "code", name]
    frames.append(s)

if not frames:
    raise RuntimeError("No factor data returned. Check GM terminal connection.")

truth = frames[0]
for f in frames[1:]:
    truth = truth.merge(f, on=["date", "code"], how="outer")

# ── 导出 ──

output = "jq_gm_truth.csv"
truth.to_csv(output, index=False, encoding="utf-8-sig")

print(f"\nDone: {output}")
print(f"  Rows:    {len(truth)}")
print(f"  Columns: {len(truth.columns)}")
print(f"  First 5 factor columns: {list(truth.columns[2:7])}")
print(f"  Non-null values: {truth.notna().sum().sum()} / {truth.size}")
print(f"\nSave this file:")
print(f"  ~/Desktop/agentmatrix-research/data/factor_lab/jq_gm_truth.csv")
