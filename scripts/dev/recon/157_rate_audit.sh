RUN=/home/data/agentmatrix_run
echo "=== 最近 12 个分片的完成时刻与间隔 ==="
for f in "$RUN"/logs/shard*.log; do
  ts=$(grep -o '### shard[0-9]* done [0-9T:+-]*' "$f" 2>/dev/null | head -1 | awk '{print $4}')
  tag=$(basename "$f" .log)
  [ -n "$ts" ] && echo "$ts $tag"
done | sort | tail -12 > "$RUN/rehearsal/recent_done.txt"
cat "$RUN/rehearsal/recent_done.txt" | sed 's/^/  /'
echo
/home/data/conda-envs/rqsdk/bin/python -X utf8 - <<'PYEOF'
from datetime import datetime
rows = []
for line in open("/home/data/agentmatrix_run/rehearsal/recent_done.txt"):
    ts, tag = line.split()
    rows.append((datetime.fromisoformat(ts), tag))
rows.sort()
print("  间隔:")
for i in range(1, len(rows)):
    gap = (rows[i][0] - rows[i-1][0]).total_seconds()
    print("    %s → %s : %5.0f s (%.1f 片/小时)" % (
        rows[i-1][1], rows[i][1], gap, 3600/gap if gap else 0))
import statistics
gaps = [(rows[i][0]-rows[i-1][0]).total_seconds() for i in range(1, len(rows))]
print()
print("  中位间隔 %.0f s → %.1f 片/小时（上限 6.4）" % (
    statistics.median(gaps), 3600/statistics.median(gaps)))
PYEOF
echo
echo "=== 是否有我自己的重负载在跑（会与分片抢 CPU）==="
ps -eo pid,pcpu,etime,args --sort=-pcpu | head -6 | cut -c1-120 | sed 's/^/  /'
date -Is
