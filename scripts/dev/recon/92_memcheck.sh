RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
OUT=$RUN/rehearsal/memcheck.log
cat > "$RUN/rehearsal/memcheck.sh" <<'EOF'
#!/usr/bin/env bash
REPO=/home/data/agentmatrix_run/agentmatrix
PY=/home/data/conda-envs/rqsdk/bin/python
export PYTHONPATH=$REPO
cd $REPO || exit 1
echo "start $(date -Is)"
/usr/bin/time -f "MEMCHECK wall=%es maxrss=%MkB" \
  $PY -X utf8 -u - <<'PYEOF'
import glob, sys, time
sys.path.insert(0, "/home/data/agentmatrix_run/agentmatrix")
import pyarrow.parquet as pq
from research_core.factor_lab.streaming_supplement import (
    ranked_block, composite_scores, correlation_from_block,
)

parts = sorted(glob.glob("/home/data/agentmatrix_run/delivery/values/parts/*.parquet"))
ids = set()
for p in parts:
    ids.update(str(n) for n in pq.read_table(p, columns=["factor_name"]).column(0).to_pylist())
ids = sorted(ids)
print("parts=%d  factors=%d" % (len(parts), len(ids)))

t0 = time.time()
block = ranked_block(parts, factor_ids=ids)
print("ranked_block: %s rows x %d factors, %.1fs" % (format(block.n_rows, ","), len(block.factor_ids), time.time() - t0))

# The fix under test: this used to allocate rows x factors x 8 bytes as float64.
t0 = time.time()
scores = composite_scores(block, columns=ids, directions={f: 1.0 for f in ids})
print("composite over ALL %d factors: %.1fs, rows=%s" % (len(ids), time.time() - t0, format(len(scores), ",")))
del scores

t0 = time.time()
corr = correlation_from_block(block)
print("correlation: %.1fs dates_used=%d missing=%d maxdiff=%.4f" % (
    time.time() - t0, corr.dates_used, len(corr.factors_missing), corr.max_pooled_difference))
PYEOF
echo "exit=$? $(date -Is)"
EOF
sed -i 's/\r$//' "$RUN/rehearsal/memcheck.sh"
chmod +x "$RUN/rehearsal/memcheck.sh"
setsid nohup bash "$RUN/rehearsal/memcheck.sh" > "$OUT" 2>&1 < /dev/null &
echo "  已启动（detached）: $OUT"
sleep 20
cat "$OUT"
date -Is
