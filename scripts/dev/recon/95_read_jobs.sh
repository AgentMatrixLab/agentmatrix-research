RUN=/home/data/agentmatrix_run
echo "=== jobs_check 结果（去掉逐因子进度行）==="
grep -vE 'neutral-IC ' "$RUN/rehearsal/jobs_check.log" 2>/dev/null | tail -18
echo
echo "=== pool 进度 ==="
echo "  oos 完成: $(ls $RUN/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l) / 213"
echo "  parts: $(ls $RUN/delivery/values/parts/*.parquet 2>/dev/null | wc -l)"
ps -eo pid,etime,args | awk '/run_one_shard\.sh [0-9]/ {print "  arg=" $NF, "etime=" $2}'
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
free -g | head -2
date -Is
