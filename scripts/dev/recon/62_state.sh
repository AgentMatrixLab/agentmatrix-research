RUN=/home/data/agentmatrix_run
echo "=== 1. 进程 (pool / shard / python) ==="
ps -eo pid,ppid,etime,rss,pcpu,args --sort=start_time | grep -E 'run_pool|run_one_shard|xargs|sharded_driver|factor' | grep -v grep
echo
echo "--- bash 命令行匹配 run_ 的进程（安全查看法）---"
ps -eo pid,ppid,etime,rss,args | awk '$2=="bash" || $3 ~ /run_/ {print}' | head -20
echo
echo "=== 2. 负载 / 内存 / 磁盘 ==="
uptime
free -g
df -h $RUN /home/data
echo
echo "=== 3. 分片完成情况 ==="
echo "  oos 完成 : $(ls $RUN/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l) / 213"
echo "  train 完成: $(ls $RUN/shards/shard*/train/batch_manifest.json 2>/dev/null | wc -l)"
echo "  分片目录 : $(ls -d $RUN/shards/shard* 2>/dev/null | wc -l)"
echo
echo "=== 4. 最近完成的分片（按 mtime，含间隔）==="
/home/data/conda-envs/rqsdk/bin/python -X utf8 - <<'PYEOF'
import glob, os, datetime
RUN = "/home/data/agentmatrix_run"
items = []
for p in glob.glob(RUN + "/shards/shard*/oos/batch_manifest.json"):
    m = os.path.getmtime(p)
    items.append((m, os.path.basename(os.path.dirname(os.path.dirname(p)))))
items.sort()
now = datetime.datetime.now().timestamp()
print("  共 %d 片，最早 %s，最新 %s" % (
    len(items),
    datetime.datetime.fromtimestamp(items[0][0]).strftime("%m-%d %H:%M") if items else "-",
    datetime.datetime.fromtimestamp(items[-1][0]).strftime("%m-%d %H:%M") if items else "-"))
prev = None
for m, tag in items:
    dt = "" if prev is None else "  (+%.1f min)" % ((m - prev) / 60)
    print("   %s  %s%s" % (datetime.datetime.fromtimestamp(m).strftime("%m-%d %H:%M"), tag, dt))
    prev = m
if items:
    span = (items[-1][0] - items[0][0]) / 3600.0
    n = len(items) - 1
    rate = (n / span) if span > 0 else 0
    print()
    print("  实测速率: %.2f 片/小时 (基于 %d 个间隔, 跨度 %.1f h)" % (rate, n, span))
    print("  距上次完成: %.1f 分钟" % ((now - items[-1][0]) / 60))
PYEOF
echo
echo "=== 5. 日志文件 ==="
ls -la $RUN/logs/ 2>/dev/null | head -40
echo
echo "--- 每个日志最后修改时间 ---"
for f in $RUN/logs/*; do
  [ -f "$f" ] && echo "  $(stat -c '%y' "$f" | cut -c1-19)  $(basename $f)  ($(stat -c %s "$f") B)"
done
echo
echo "=== 6. 候选清单家族分布（顺序敏感）==="
/home/data/conda-envs/rqsdk/bin/python -X utf8 - <<'PYEOF'
import csv, collections
rows = list(csv.DictReader(open("/home/data/agentmatrix_run/candidate_list.csv", encoding="utf-8")))
print("  总候选: %d" % len(rows))
fams = collections.Counter(r["factor_id"].split(":")[0] for r in rows)
# order of first appearance
seen = []
for r in rows:
    f = r["factor_id"].split(":")[0]
    if f not in seen:
        seen.append(f)
print("  家族出现顺序与该家族的候选数:")
cum = 0
for f in seen:
    print("    %-12s %4d  (累计到 %d)" % (f, fams[f], cum + fams[f]))
    cum += fams[f]
PYEOF
date -Is
