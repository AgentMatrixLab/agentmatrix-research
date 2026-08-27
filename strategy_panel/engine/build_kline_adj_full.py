"""
用 adj_factor 的最后因子填充 kline_1d 中 4月10日之后的原始价格，
生成复权的 kline_adj_full.parquet，覆盖到最新日期。
"""
import os, sys
import pandas as pd
import numpy as np
from datetime import datetime

DATA_DIR = r"D:\bigquant\custom_engine\data"
KLINE_RAW = os.path.join(DATA_DIR, "kline_1d.parquet")
ADJ_PATH = os.path.join(DATA_DIR, "adj_factor.parquet")
OUT_PATH = os.path.join(DATA_DIR, "kline_adj_full.parquet")
KLINE_ADJ_OLD = os.path.join(DATA_DIR, "kline_adj.parquet")  # 旧的复权数据(到4月9)

print("=" * 50)
print("[ADJ-BUILD] 构建覆盖到最新日期的复权K线...")
print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# 1. 读原始 K线
raw = pd.read_parquet(KLINE_RAW)
if raw["trade_date"].dtype == "uint16":
    raw["trade_date"] = pd.to_datetime(raw["trade_date"], unit="D", origin="unix")
print(f"  原始K线: {len(raw)} 行, {raw['symbol'].nunique()} 只, "
      f"{raw['trade_date'].min().date()} -> {raw['trade_date'].max().date()}")

# 2. 读旧的复权K线（有 adj_factor + open_adj/high_adj/low_adj/close_adj，到4月9）
if os.path.exists(KLINE_ADJ_OLD):
    old_adj = pd.read_parquet(KLINE_ADJ_OLD)
    if old_adj["trade_date"].dtype == "uint16":
        old_adj["trade_date"] = pd.to_datetime(old_adj["trade_date"], unit="D", origin="unix")
    print(f"  旧复权K线: {len(old_adj)} 行, {old_adj['trade_date'].max().date()}")
    # 只保留4月10日之前的（回测部分）
    old_adj = old_adj[old_adj["trade_date"] <= pd.Timestamp("2026-04-10")]
    print(f"  截取到4月10日前: {len(old_adj)} 行")
else:
    old_adj = pd.DataFrame()
    print("  旧复权K线不存在，全部从头算")

# 3. 读复权因子，取每个股票最后一次因子
adj = pd.read_parquet(ADJ_PATH)
if adj["trade_date"].dtype == "uint16":
    adj["trade_date"] = pd.to_datetime(adj["trade_date"], unit="D", origin="unix")
print(f"  复权因子: {len(adj)} 行, {adj['trade_date'].max().date()}")

# 取每只股票的最后一次复权因子
last_adj = adj.sort_values("trade_date").groupby("symbol").last()[["adj_factor"]].reset_index()
last_adj = last_adj.rename(columns={"adj_factor": "last_adj_factor"})
print(f"  最后因子: {len(last_adj)} 只")

# 4. 取4月10日之后的原始数据
raw_new = raw[raw["trade_date"] > pd.Timestamp("2026-04-09")].copy()
print(f"  4月10日后原始数据: {len(raw_new)} 行, "
      f"{raw_new['trade_date'].min().date()} -> {raw_new['trade_date'].max().date()}")

# 5. Merge 因子
raw_new = raw_new.merge(last_adj, on="symbol", how="left")
missing = raw_new["last_adj_factor"].isna().sum()
if missing > 0:
    print(f"  缺因子: {missing} 行, 用 1.0 填充")
    raw_new["last_adj_factor"] = raw_new["last_adj_factor"].fillna(1.0)

# 6. 计算复权价格
for col in ["open", "high", "low", "close"]:
    raw_new[f"{col}_adj"] = raw_new[col] / raw_new["last_adj_factor"]

# 7. 设置 adj_factor 列
raw_new["adj_factor"] = raw_new["last_adj_factor"]

# 8. 合并旧复权 + 新复权
# 确保列对齐
needed_cols = ["symbol", "trade_date", "bar_time", "open", "high", "low", "close",
               "volume", "amount", "source", "batch_id", "ingest_time",
               "adj_factor", "open_adj", "high_adj", "low_adj", "close_adj"]

if len(old_adj) > 0:
    # 确保 old_adj 有所需列
    for c in needed_cols:
        if c not in old_adj.columns:
            old_adj[c] = np.nan
    old_part = old_adj[needed_cols].copy()
else:
    old_part = pd.DataFrame(columns=needed_cols)

new_part = raw_new[needed_cols].copy()

result = pd.concat([old_part, new_part], ignore_index=True)
result = result.sort_values(["trade_date", "symbol"])
# 去重：新算的复权数据覆盖同日同股旧数据
result = result.drop_duplicates(subset=["symbol", "trade_date"], keep="last")
result = result.reset_index(drop=True)

print(f"  合并后: {len(result)} 行, {result['trade_date'].min().date()} -> {result['trade_date'].max().date()}")

# 9. 保存
result.to_parquet(OUT_PATH, index=False)
print(f"  保存: {OUT_PATH} ({os.path.getsize(OUT_PATH)/1024/1024:.1f} MB)")

# 10. 替换 kline_adj.parquet（引擎优先读这个）
if os.path.exists(KLINE_ADJ_OLD):
    bak = KLINE_ADJ_OLD + ".bak"
    if not os.path.exists(bak):
        os.rename(KLINE_ADJ_OLD, bak)
        print(f"  旧kline_adj备份: {bak}")

if os.path.exists(KLINE_ADJ_OLD):
    os.remove(KLINE_ADJ_OLD)
os.rename(OUT_PATH, KLINE_ADJ_OLD)
print(f"  已替换: {KLINE_ADJ_OLD}")

print("[OK] 复权K线已更新到最新日期")
