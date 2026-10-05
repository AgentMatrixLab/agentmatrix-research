RUN=/home/data/agentmatrix_run
echo "=== 留存状态 ==="
cat "$RUN/delivery/values/retain_status.json" 2>/dev/null
echo
echo "raw 链接:"; ls -la "$RUN/delivery/values/raw/" 2>/dev/null | head -6
echo "parts:"; ls -la "$RUN/delivery/values/parts/" 2>/dev/null | head -6
echo
echo "=== retain 守护日志尾部 ==="
tail -14 "$RUN/logs/retain_daemon.log" 2>/dev/null
echo
echo "=== 镜像状态 ==="
head -14 "$RUN/runtime_mirror/mirror_status.json" 2>/dev/null
echo
echo "=== pool 进度 ==="
echo "  oos 完成: $(ls $RUN/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l) / 213"
echo "  已移开的 run1 分片: $(ls -d $RUN/reference/run1/shard*_run1 2>/dev/null | wc -l)"
echo "  最近日志:"
ls -la "$RUN/logs/" 2>/dev/null | tail -8
echo "  在跑分片:"
ps -eo pid,etime,args | awk '/run_one_shard\.sh [0-9]/ {print "    pid=" $1, "etime=" $2, "shard=" $NF}'
echo
echo "=== 抽查一个新完成分片的 code_commit（应为 pinned 40 位）==="
/home/data/conda-envs/rqsdk/bin/python -X utf8 - <<'PYEOF'
import glob, json
paths = sorted(glob.glob("/home/data/agentmatrix_run/shards/shard*/oos/batch_manifest.json"))
print("  完成的 oos manifest 数:", len(paths))
for p in paths:
    pl = json.load(open(p))
    print("   ", p.split("/")[-3], pl.get("code_commit"), "len=", len(str(pl.get("code_commit"))))
PYEOF
echo
echo "=== 磁盘/内存 ==="
df -h / | awk 'NR==2{print "  磁盘可用: "$4" / "$2}'
free -g | head -2
date -Is
