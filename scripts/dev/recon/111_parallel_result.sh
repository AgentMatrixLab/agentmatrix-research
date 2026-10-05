RUN=/home/data/agentmatrix_run
echo "=== 并行构建验证结果 ==="
tail -16 "$RUN/rehearsal/parallel_build2.log" 2>/dev/null
echo
echo "=== 该彩排进程是否还在 ==="
ps -eo pid,etime,args | awk '$0 !~ /awk/ && /rehearsal\/parallel2/ {print "  " $1, $2, substr($0, index($0,$3), 70)}'
echo
echo "=== pool 单分片阶段耗时（最近 5 片）==="
for i in 023 024 025 026 027; do
  f="$RUN/logs/shard$i.log"
  [ -f "$f" ] || continue
  echo "  --- shard$i"
  grep -E 'start |build wall|train wall|oos wall|done ' "$f" 2>/dev/null | sed 's/^/     /'
done
echo
echo "=== 累计通过率 ==="
/home/data/conda-envs/rqsdk/bin/python -X utf8 - <<'PYEOF'
import glob, json
total = passed = 0
for p in glob.glob("/home/data/agentmatrix_run/shards/shard*/oos/batch_manifest.json"):
    for r in json.load(open(p)).get("results", []):
        total += 1
        if r.get("status") == "validated" and not r.get("failed_gates"):
            passed += 1
print("  因子结果 %d, 通过 %d (%.1f%%)" % (total, passed, 100.0 * passed / max(total, 1)))
PYEOF
date -Is
