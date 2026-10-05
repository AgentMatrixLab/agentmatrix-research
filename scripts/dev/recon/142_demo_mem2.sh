RUN=/home/data/agentmatrix_run
OUT=$RUN/rehearsal/demo_mem2.log
cat > "$RUN/rehearsal/demo_mem2.sh" <<'EOF'
#!/usr/bin/env bash
RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
PY=/home/data/conda-envs/rqsdk/bin/python
cd $REPO || exit 1
export PYTHONPATH=$REPO
echo "start $(date -Is)"
echo "  真实合并文件: $RUN/delivery/rebuild/factor_values.parquet ($(du -h $RUN/delivery/rebuild/factor_values.parquet | cut -f1))"

$PY -X utf8 -u - <<'PYEOF'
"""Measure the demo's two heavy steps on the REAL consolidated factor table.

An earlier synthetic attempt was misleading: building 155M rows by pandas concat with a
per-row factor-name string peaked at 22.5 GB before any work started, which is an artefact of
the construction, not of the code path. The real path streams from parquet.

So this runs the actual functions against the actual 74-factor file the chain produced, and
reports the process's own peak RSS. The block is linear in factors, which is what allows
extrapolation to a delivered set of ~310.
"""
import resource
import time

from research_core.factor_lab.streaming_supplement import (
    correlation_from_block,
    ranked_block,
)

PATH = "/home/data/agentmatrix_run/delivery/rebuild/factor_values.parquet"
import json
side = json.load(open(PATH + ".json"))
factor_ids = sorted(side["factors"])
n_factors = len(factor_ids)
rows = side["row_count"] // n_factors


def peak_gb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6


print(f"  factors={n_factors}  rows/series={rows:,}  total rows={side['row_count']:,}")
print(f"  baseline peak {peak_gb():.2f} GB")

started = time.perf_counter()
block = ranked_block([PATH], factor_ids=factor_ids)
read_s = time.perf_counter() - started
print(f"  ranked_block            : {read_s:.1f}s  peak {peak_gb():.2f} GB")
print(f"    ranks shape={block.ranks.shape}  dtype={block.ranks.dtype}")

started = time.perf_counter()
corr = correlation_from_block(block)
corr_s = time.perf_counter() - started
print(f"  correlation_from_block  : {corr_s:.1f}s  peak {peak_gb():.2f} GB")
print(f"    matrix={corr.correlation.shape}")

peak = peak_gb()
per_factor = peak / n_factors
print()
print(f"  实测 {n_factors} 因子：峰值 {peak:.2f} GB（约 {per_factor * 1000:.0f} MB/因子）")
for target in (150, 310, 450):
    print(f"  ⇒ 外推 {target} 因子：峰值 ≈ {peak * target / n_factors:.1f} GB，"
          f"读取 ≈ {read_s * target / n_factors / 60:.1f} min")
print()
print(f"  参考：float32 block 本身在 310 因子时为 "
      f"{310 * rows * 4 / 1e9:.1f} GB；池停止后可用内存约 55 GB")
PYEOF
echo "exit=$?"
echo "done $(date -Is)"
EOF
sed -i 's/\r$//' "$RUN/rehearsal/demo_mem2.sh"
chmod +x "$RUN/rehearsal/demo_mem2.sh"
setsid nohup bash "$RUN/rehearsal/demo_mem2.sh" > "$OUT" 2>&1 < /dev/null &
echo "  已启动（detached）"
date -Is
