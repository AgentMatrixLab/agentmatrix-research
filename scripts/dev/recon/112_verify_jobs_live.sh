RUN=/home/data/agentmatrix_run
echo "=== 1. 昂贵分片串行 vs 并行（决定性）==="
tail -12 "$RUN/rehearsal/parallel_build2.log" 2>/dev/null
echo
echo "=== 2. 新启动的分片是否真的在用并行构建 ==="
for i in 026 027 028 029 030; do
  f="$RUN/logs/shard$i.log"
  [ -f "$f" ] || continue
  j=$(grep -c 'building with' "$f" 2>/dev/null || echo 0)
  w=$(grep -o 'build wall=[0-9.]*s' "$f" 2>/dev/null | head -1)
  printf "  shard%s: 并行标记=%s  %s\n" "$i" "$j" "${w:-（build 未完成）}"
done
echo
echo "=== 3. 进度 ==="
echo "  oos 完成: $(ls $RUN/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l) / 213"
echo "  parts   : $(ls $RUN/delivery/values/parts/*.parquet 2>/dev/null | wc -l)"
ps -eo pid,etime,args | awk '/run_one_shard\.sh [0-9]/ {print "    arg=" $NF, "etime=" $2}'
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
echo
echo "=== 4. 守护进程 ==="
ps -eo pid,etime,args | awk '/retain_passing_values|mirror_runtime_data/ && !/awk/ {print "  " $1, $2}'
date -Is
