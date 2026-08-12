"""重建 Qlib bin 数据 v5 — 纯numpy矩阵方案, 无groupby, 低内存

核心: 一次性构建 (n_dates × n_syms) 的 close 矩阵 (~33MB),
再逐列写入 .day.bin 文件。
"""
import os, sys, time, gc
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
sys.path.insert(0, '.')
import numpy as np
import pandas as pd
from pathlib import Path
import struct, json, shutil

from config import QLIB_BIN_DIR

qlib_dir = Path(QLIB_BIN_DIR)
DATA = "data"

def to_qlib_arr(sym_series):
    return sym_series.str.replace('.XSHE', '.SZ', regex=False).str.replace('.XSHG', '.SH', regex=False)

# ======== 1. 日历 ========
print("[1] 日历...", flush=True)
cal = pd.read_parquet(os.path.join(DATA, "calendar.parquet"))
cal['trade_date'] = pd.to_datetime(cal['trade_date'])
cal_dates = sorted(cal['trade_date'].dt.strftime("%Y-%m-%d").tolist())
n_dates = len(cal_dates)
del cal
gc.collect()
print(f"  {n_dates}天 ({cal_dates[0]} -> {cal_dates[-1]})", flush=True)

(qlib_dir / "calendars").mkdir(parents=True, exist_ok=True)
(qlib_dir / "calendars" / "day.txt").write_text("\n".join(cal_dates))

# ======== 2. 加载 lean K线 ========
print("[2] 加载 lean K线...", flush=True)
t0 = time.time()
kline = pd.read_parquet(os.path.join(DATA, "kline_adj_lean.parquet"))
kline['trade_date'] = pd.to_datetime(kline['trade_date'])
kline['symbol'] = to_qlib_arr(kline['symbol'])
kline['date_str'] = kline['trade_date'].dt.strftime('%Y-%m-%d')
print(f"  {len(kline):,}行, {time.time()-t0:.1f}s", flush=True)

# ======== 3. 向量化构建 close 矩阵 ========
print("[3] 构建 close 矩阵...", flush=True)
t0 = time.time()

date_cat = pd.Categorical(kline['date_str'], categories=cal_dates)
sym_cat = pd.Categorical(kline['symbol'])
symbols = list(sym_cat.categories)
n_syms = len(symbols)

rows = date_cat.codes          # 日期索引 (-1 = 不在日历内)
cols = sym_cat.codes           # 股票索引
vals = kline['close_adj'].to_numpy(dtype=np.float32)

# 过滤无效日期
valid = rows >= 0
rows = rows[valid]
cols = cols[valid]
vals = vals[valid]

mat = np.full((n_dates, n_syms), np.nan, dtype=np.float32)
mat[rows, cols] = vals   # 向量化填充

print(f"  矩阵: {mat.shape}, {mat.nbytes/1024/1024:.0f}MB, "
      f"非NaN: {np.sum(~np.isnan(mat)):,}, {time.time()-t0:.1f}s", flush=True)

del kline, date_cat, sym_cat, rows, cols, vals, valid
gc.collect()

# ======== 4. instruments ========
print("[4] instruments...", flush=True)
(qlib_dir / "instruments").mkdir(parents=True, exist_ok=True)
lines = [f"{s}\t{cal_dates[0]}\t{cal_dates[-1]}" for s in symbols]
lines.append(f"SH000300\t{cal_dates[0]}\t{cal_dates[-1]}")
(qlib_dir / "instruments" / "all.txt").write_text("\n".join(lines))
print(f"  {n_syms}只 + SH000300")

# ======== 5. 写 features ========
print("[5] 写特征文件...", flush=True)
feat_dir = qlib_dir / "features"
if feat_dir.exists():
    # Windows 竞态: rmtree 可能因文件句柄延迟失败, 重试3次
    for attempt in range(3):
        try:
            shutil.rmtree(str(feat_dir))
            break
        except OSError as e:
            print(f"  rmtree 重试{attempt+1}: {e}", flush=True)
            time.sleep(2)
feat_dir.mkdir(parents=True, exist_ok=True)

arr_ones = np.ones(n_dates, dtype=np.float32)
hdr = struct.pack("<f", 0.0)
t0 = time.time()

for si, sym in enumerate(symbols):
    sym_dir = feat_dir / sym
    sym_dir.mkdir(parents=True, exist_ok=True)
    with open(sym_dir / "close.day.bin", "wb") as fp:
        fp.write(hdr)
        mat[:, si].tofile(fp)
    with open(sym_dir / "factor.day.bin", "wb") as fp:
        fp.write(hdr)
        arr_ones.tofile(fp)
    if (si + 1) % 1000 == 0:
        print(f"\r  [{si+1}/{n_syms}] ({time.time()-t0:.0f}s)", end='', flush=True)

print(f"\r  [{n_syms}/{n_syms}] 完成 ({time.time()-t0:.0f}s)")

# ======== 6. 基准 ========
print("[6] 基准...", flush=True)
with np.errstate(invalid='ignore'):
    daily_avg = np.nanmean(mat, axis=1)
daily_avg = np.where(np.isnan(daily_avg), 0, daily_avg).astype(np.float32)

bench_dir = feat_dir / "sh000300"
bench_dir.mkdir(parents=True, exist_ok=True)
for fname in ['close', 'open']:
    with open(bench_dir / f"{fname}.day.bin", "wb") as fp:
        fp.write(hdr)
        daily_avg.tofile(fp)
with open(bench_dir / "factor.day.bin", "wb") as fp:
    fp.write(hdr)
    arr_ones.tofile(fp)
print("  sh000300 done")

# ======== 7. Manifest + 验证 ========
manifest = {
    "converted_at": pd.Timestamp.now().isoformat(),
    "symbol_count": n_syms,
    "feature_count": 2,
    "features": ["close", "factor"],
    "date_start": cal_dates[0],
    "date_end": cal_dates[-1],
    "total_dates": n_dates,
}
(qlib_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))

print("[7] 验证...", flush=True)
zero_syms = np.sum(np.all(np.isnan(mat) | (mat == 0), axis=0))
print(f"  矩阵列统计: 全零/全NaN股票 = {zero_syms}/{n_syms}")
# 抽查文件
for probe in ['000001.SZ', '600519.SH']:
    p = feat_dir / probe / 'close.day.bin'
    if p.exists():
        arr = np.fromfile(p, offset=4, dtype=np.float32)
        print(f"  {probe}: {(arr>0).sum()}/{len(arr)} 非零")

print(f"\n{'='*50}\n完成: {n_syms}只股票, {n_dates}天\n{'='*50}")
