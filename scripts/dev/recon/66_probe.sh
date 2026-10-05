RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
PY=/home/data/conda-envs/rqsdk/bin/python
PROBE=$RUN/scratch/rebuild_probe
mkdir -p "$PROBE"

echo "=== 在跑分片的 factor_values.parquet 大小（决定能否用硬链接留存）==="
ls -la $RUN/shards/shard010/factor_values.parquet $RUN/shards/shard011/factor_values.parquet 2>/dev/null
echo
echo "=== 面板大小 ==="
ls -la $RUN/panel/validation_panel.parquet
echo
echo "=== 已通过因子的数量（用于探针）==="
$PY -X utf8 - <<'PYEOF'
import glob, json, csv
rows = []
for p in sorted(glob.glob("/home/data/agentmatrix_run/shards/shard*/oos/batch_manifest.json")):
    rows.extend(json.load(open(p)).get("results", []))
passed = [r["factor_id"] for r in rows
          if r.get("status") == "validated" and not r.get("failed_gates")]
print("passing:", len(passed))
src = "/home/data/agentmatrix_run/candidate_list.csv"
out = "/home/data/agentmatrix_run/scratch/rebuild_probe/candidates.csv"
with open(src, encoding="utf-8", newline="") as fh:
    rdr = csv.DictReader(fh)
    fields = list(rdr.fieldnames)
    keep = [r for r in rdr if r["factor_id"] in set(passed)]
with open(out, "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=fields)
    w.writeheader()
    w.writerows(keep)
print("wrote %s with %d rows" % (out, len(keep)))
PYEOF

echo
echo "=== 启动重建探针（后台，nice 15，OOM 优先级最高以便被杀的是它而不是分片 worker）==="
cat > "$PROBE/run.sh" <<'EOF'
#!/usr/bin/env bash
RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
PY=/home/data/conda-envs/rqsdk/bin/python
PROBE=$RUN/scratch/rebuild_probe
cd "$REPO" || exit 1
export PYTHONPATH="$REPO"
echo 1000 > /proc/self/oom_score_adj 2>/dev/null
/usr/bin/time -f "PROBE build wall=%es maxrss=%MkB" \
  nice -n 15 "$PY" -X utf8 -u scripts/build_factor_values.py \
    --candidates "$PROBE/candidates.csv" \
    --panel-file "$RUN/panel/validation_panel.parquet" \
    --config "$REPO/configs/validation_gates.yaml" \
    --output "$PROBE/factor_values.parquet" \
    --report "$PROBE/build_report.json" \
    --emit-start 2020-01-02
echo "PROBE exit=$?"
ls -la "$PROBE/factor_values.parquet" 2>/dev/null
echo "PROBE done $(date -Is)"
EOF
sed -i 's/\r$//' "$PROBE/run.sh"
chmod +x "$PROBE/run.sh"
setsid nohup bash "$PROBE/run.sh" > "$PROBE/probe.log" 2>&1 < /dev/null &
echo "  probe pid=$!"
sleep 5
echo "  probe.log so far:"; cat "$PROBE/probe.log"
date -Is
