RUN=/home/data/agentmatrix_run
echo "=== 外部 agent 的 rebuild 进程（每 60 秒采一次，共 5 次）==="
for i in 1 2 3 4 5; do
  p=$(ps -eo pcpu,etime,rss,args | awk '/rebuild_passing_factors/ && !/awk/ && /python/ {printf "cpu=%s%% etime=%s rss=%.1fGB", $1, $2, $3/1048576; exit}')
  a=$(free -g | awk '/^Mem:/{print $7}')
  z=$(du -sh "$RUN/delivery_dryrun" 2>/dev/null | cut -f1)
  echo "  $(date '+%H:%M:%S')  rebuild[${p:-无}]  可用内存=${a}GB  dryrun=${z:-0}"
  [ "$i" -lt 5 ] && sleep 60
done
echo
echo "=== 分片速率（最近 6 个间隔）==="
for f in "$RUN"/logs/shard*.log; do
  d=$(grep -o '### shard[0-9]* done [0-9T:+-]*' "$f" 2>/dev/null | head -1 | awk '{print $4}')
  [ -n "$d" ] && echo "$d"
done | sort | tail -7 > "$RUN/rehearsal/rate_tmp.txt"
/home/data/conda-envs/rqsdk/bin/python -X utf8 - <<'PYEOF'
from datetime import datetime
rows = [datetime.fromisoformat(l.strip()) for l in open("/home/data/agentmatrix_run/rehearsal/rate_tmp.txt") if l.strip()]
for i in range(1, len(rows)):
    gap = (rows[i] - rows[i-1]).total_seconds()
    print("  %s → %s : %5.0f s" % (rows[i-1].strftime("%H:%M"), rows[i].strftime("%H:%M"), gap))
PYEOF
echo "  参考：便宜分片 cadence 559 s（= 一个 oos 相位）"
date -Is
