RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
PY=/home/data/conda-envs/rqsdk/bin/python
MARK=mark_2c91_retain_restart

echo "=== 1. 清理滞留的硬链接（旧版本 daemon 不会回收）==="
$PY -X utf8 - <<'PYEOF'
import os, glob
raw = "/home/data/agentmatrix_run/delivery/values/raw"
parts = {os.path.basename(p) for p in glob.glob("/home/data/agentmatrix_run/delivery/values/parts/*.parquet")}
freed = 0
removed = []
for link in glob.glob(raw + "/*.parquet"):
    if os.path.basename(link) in parts:
        size = os.path.getsize(link)
        os.unlink(link)
        freed += size
        removed.append(os.path.basename(link))
print("  删除滞留链接:", removed)
print("  释放: %.2f GB" % (freed / 1e9))
PYEOF

echo
echo "=== 2. 重启留存守护（带修复版本）==="
EXISTING=$(ps -eo pid,args | awk -v m="$MARK" '$0 !~ m && /retain_passing_values\.py/ && /interval/ {print $1}')
for pid in $EXISTING; do echo "  停掉旧守护 $pid"; kill -TERM "$pid" 2>/dev/null; done
sleep 2
setsid nohup $PY -X utf8 "$RUN/retain_passing_values.py" --repo "$REPO" --interval 20 \
  > "$RUN/logs/retain_daemon.log" 2>&1 < /dev/null &
sleep 25
echo "  守护进程:"
ps -eo pid,etime,args | awk -v m="$MARK" '$0 !~ m && /retain_passing_values/ {print "    " $1, $2, $4, $5, $6, $7}'

echo
echo "=== 3. 现状 ==="
cat "$RUN/delivery/values/retain_status.json" 2>/dev/null
echo
echo "  parts: $(ls $RUN/delivery/values/parts/*.parquet 2>/dev/null | wc -l)  raw链接: $(ls $RUN/delivery/values/raw/*.parquet 2>/dev/null | wc -l)"
du -sh $RUN/delivery/values 2>/dev/null
echo
echo "=== 4. 流式模块新版本自检（真实 parts 上）==="
cd $REPO || exit 1
export PYTHONPATH=$REPO
$PY -X utf8 - <<'PYEOF'
import sys, glob, time
sys.path.insert(0, "/home/data/agentmatrix_run/agentmatrix")
from research_core.factor_lab.streaming_supplement import (
    ranked_block, composite_scores, correlation_from_block,
)
parts = sorted(glob.glob("/home/data/agentmatrix_run/delivery/values/parts/*.parquet"))
ids = []
# Read factor names cheaply from the parts' first row group.
import pyarrow.parquet as pq
for p in parts:
    t = pq.read_table(p, columns=["factor_name"])
    for n in set(t.column("factor_name").to_pylist()):
        ids.append(str(n))
ids = sorted(set(ids))
print("  parts=%d  因子数=%d" % (len(parts), len(ids)))
t0 = time.time()
block = ranked_block(parts, factor_ids=ids)
print("  ranked_block: %d 行 x %d 因子, %.1fs" % (block.n_rows, len(block.factor_ids), time.time() - t0))

# The memory fix: one column at a time rather than a full float64 copy of the block.
t0 = time.time()
scores = composite_scores(block, columns=ids, directions={f: 1.0 for f in ids})
print("  composite over ALL %d factors: %.1fs, rows=%s" % (len(ids), time.time() - t0, format(len(scores), ",")))
t0 = time.time()
corr = correlation_from_block(block)
print("  correlation: %.1fs, dates_used=%d, missing=%s" % (
    time.time() - t0, corr.dates_used, corr.factors_missing))
print("  max |daily-average - pooled| = %.4f" % corr.max_pooled_difference)
PYEOF
date -Is
