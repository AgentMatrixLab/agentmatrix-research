RUN=/home/data/agentmatrix_run
OUT=$RUN/rehearsal/demo_mem.log
cat > "$RUN/rehearsal/demo_mem.sh" <<'EOF'
#!/usr/bin/env bash
RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
PY=/home/data/conda-envs/rqsdk/bin/python
cd $REPO || exit 1
export PYTHONPATH=$REPO
echo "start $(date -Is)"

$PY -X utf8 -u - <<'PYEOF'
"""Measure the demo's two memory-hungry steps at the real factor width.

`ranked_block` builds a dense (dates x codes x factors) array and `correlation_from_block`
correlates it. Both scale linearly in rows x factors, so measuring at the true width (310
factors) with a fraction of the rows gives the full-scale figure by multiplication -- which is
the only scaling question the delivery still has, and the one that decides whether the demo
fits alongside a stopped pool's freed memory.

Peak RSS is read from the process itself, not estimated.
"""
import gc
import resource
import time

import numpy as np
import pandas as pd

from research_core.factor_lab.streaming_supplement import (
    correlation_from_block,
    ranked_block,
)

FACTORS = 310           # a plausible delivered count
ROWS_PER_FACTOR = 500_000
CODES = 5_455
DATES = 120


def peak_gb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6  # kB -> GB


rng = np.random.default_rng(7)
n = FACTORS * ROWS_PER_FACTOR
print(f"  building synthetic long table: {n:,} rows, {FACTORS} factors, "
      f"{ROWS_PER_FACTOR:,} rows each")
codes = np.array([f"{i:06d}.XSHE" for i in range(CODES)])
dates = pd.bdate_range("2020-01-02", periods=DATES)
# Reuse the same code/date grid per factor so the block is a genuine cross-section.
rep = ROWS_PER_FACTOR // DATES
frame = pd.DataFrame({
    "date": np.tile(dates, CODES * rep)[:ROWS_PER_FACTOR],
    "code": np.repeat(codes, rep)[:ROWS_PER_FACTOR],
})
del rep
base = rng.normal(size=len(frame)).astype("float64")
long_frames = []
for f in range(FACTORS):
    part = frame.copy()
    part["factor_name"] = f"SYN:factor{f:03d}"
    part["value"] = base + rng.normal(scale=0.05, size=len(frame))
    long_frames.append(part)
table = pd.concat(long_frames, ignore_index=True)
del long_frames, base
gc.collect()
print(f"  long table: {len(table):,} rows, peak after build {peak_gb():.1f} GB")

started = time.perf_counter()
block = ranked_block(table)
print(f"  ranked_block: {time.perf_counter() - started:.1f}s  peak {peak_gb():.1f} GB")
del table
gc.collect()

started = time.perf_counter()
corr = correlation_from_block(block)
print(f"  correlation_from_block: {time.perf_counter() - started:.1f}s  peak {peak_gb():.1f} GB")
print(f"  correlation matrix: {corr.shape}")

measured_rows = ROWS_PER_FACTOR
peak = peak_gb()
scale = 7_696_167 / measured_rows
print()
print(f"  实测：{FACTORS} 因子 x {measured_rows:,} 行，峰值 {peak:.1f} GB")
print(f"  ⇒ 全量 {FACTORS} 因子 x 7,696,167 行 外推峰值 ≈ {peak * scale:.1f} GB")
print(f"  （block 本身在 {FACTORS}x7,696,167 下约 "
      f"{FACTORS * 7_696_167 * 4 / 1e9:.1f} GB/份 float32）")
PYEOF
echo "exit=$?"
echo "done $(date -Is)"
EOF
sed -i 's/\r$//' "$RUN/rehearsal/demo_mem.sh"
chmod +x "$RUN/rehearsal/demo_mem.sh"
setsid nohup bash "$RUN/rehearsal/demo_mem.sh" > "$OUT" 2>&1 < /dev/null &
echo "  已启动（detached，约 10 分钟）"
date -Is
