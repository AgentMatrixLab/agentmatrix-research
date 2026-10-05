RUN=/home/data/agentmatrix_run
OUT=$RUN/rehearsal/stream_speed.log
cat > "$RUN/rehearsal/stream_speed.sh" <<'EOF'
#!/usr/bin/env bash
REPO=/home/data/agentmatrix_run/agentmatrix
PY=/home/data/conda-envs/rqsdk/bin/python
export PYTHONPATH=$REPO
cd $REPO || exit 1
echo "start $(date -Is)"
/usr/bin/time -f "STREAMSPEED wall=%es maxrss=%MkB" $PY -X utf8 -u - <<'PYEOF'
import glob, sys, time
sys.path.insert(0, "/home/data/agentmatrix_run/agentmatrix")
from research_core.factor_lab.factor_value_stream import iter_factor_series, RowOrderReference

parts = sorted(glob.glob("/home/data/agentmatrix_run/delivery/values/parts/*.parquet"))
print("parts:", len(parts))

t0 = time.time()
rows = 0
ref = RowOrderReference()
count = 0
for series in iter_factor_series(parts, reference=ref):
    rows += len(series)
    count += 1
elapsed = time.time() - t0
print("series read      : %d" % count)
print("rows             : %s" % format(rows, ","))
print("wall             : %.1fs" % elapsed)
print("PER SERIES       : %.2fs   (was 7.12s before the boundary-detection fix)" % (elapsed / max(count, 1)))
print("implied 450 series: %.1f min  (was ~53 min)" % (450 * elapsed / max(count, 1) / 60))
print("row-order checks : %d" % ref.comparisons)
PYEOF
echo "exit=$? $(date -Is)"
EOF
sed -i 's/\r$//' "$RUN/rehearsal/stream_speed.sh"
chmod +x "$RUN/rehearsal/stream_speed.sh"
setsid nohup bash "$RUN/rehearsal/stream_speed.sh" > "$OUT" 2>&1 < /dev/null &
echo "  已启动（detached）"
date -Is
