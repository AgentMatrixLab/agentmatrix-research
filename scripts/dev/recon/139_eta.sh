RUN=/home/data/agentmatrix_run
echo "=== 分片完成时间线（取自各分片日志，精确而非估计）==="
for f in "$RUN"/logs/shard*.log; do
  tag=$(basename "$f" .log)
  done_ts=$(grep -o '### shard[0-9]* done [0-9T:+-]*' "$f" 2>/dev/null | head -1 | awk '{print $4}')
  [ -n "$done_ts" ] && echo "$done_ts $tag"
done | sort > "$RUN/rehearsal/done_times.txt"
wc -l < "$RUN/rehearsal/done_times.txt" | sed 's/^/  已完成分片数: /'
echo
echo "  最近 15 个完成:"
tail -15 "$RUN/rehearsal/done_times.txt" | sed 's/^/    /'
echo
/home/data/conda-envs/rqsdk/bin/python -X utf8 - <<'PYEOF'
from datetime import datetime
from pathlib import Path
rows = []
for line in Path("/home/data/agentmatrix_run/rehearsal/done_times.txt").read_text().splitlines():
    ts, tag = line.split()
    rows.append((datetime.fromisoformat(ts), tag))
rows.sort()
print("  完成数:", len(rows))
if len(rows) < 3:
    raise SystemExit(0)
gaps = [(rows[i][0] - rows[i-1][0]).total_seconds() for i in range(1, len(rows))]
# 重启会制造空档，用它来剔除被中断的区间
import statistics
recent = gaps[-20:]
print("  最近 20 个间隔: 中位 %.0f s, 均值 %.0f s, 最小 %.0f s, 最大 %.0f s" % (
    statistics.median(recent), statistics.mean(recent), min(recent), max(recent)))
steady = [g for g in recent if g < 1800]
print("  剔除重启空档后（<30min）: 中位 %.0f s  均值 %.0f s  n=%d" % (
    statistics.median(steady), statistics.mean(steady), len(steady)))
rate = 3600.0 / statistics.median(steady)
print("  ⇒ 稳定速率约 %.1f 片/小时" % rate)
remaining = 213 - len(rows)
print()
print("  剩余分片: %d" % remaining)
eta_hours = remaining / rate
print("  按该速率跑完剩余分片: %.1f 小时" % eta_hours)
last = rows[-1][0]
from datetime import timedelta
print("  预计分片结束: %s" % (last + timedelta(hours=eta_hours)).strftime("%m-%d %H:%M"))
passed, total = 79, 144
rate_pass = passed / total
need = 300
shards_for_300 = need / (4 * rate_pass)
print()
print("  实测过闸率: %.1f%%" % (100 * rate_pass))
print("  交付 300 需完成分片: %.0f 片（当前 %d 片，已通过 %d 个）" % (shards_for_300, len(rows), passed))
missing = shards_for_300 - len(rows)
if missing <= 0:
    print("  ⇒ 已够 300，可以进入交付链")
else:
    print("  ⇒ 还需 %.0f 片 ≈ %.1f 小时" % (missing, missing / rate))
    print("  ⇒ 达标时刻: %s" % (last + timedelta(hours=missing / rate)).strftime("%m-%d %H:%M"))
    print("  ⇒ 加 2 小时链 → 交付约 %s" % (last + timedelta(hours=missing / rate + 2)).strftime("%m-%d %H:%M"))
PYEOF
echo
echo "=== 进度与守护 ==="
echo "  oos 完成: $(ls $RUN/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l) / 213"
echo "  parts   : $(ls $RUN/delivery/values/parts/*.parquet 2>/dev/null | wc -l)"
ps -eo pid,etime,args | awk '/run_one_shard\.sh [0-9]/ {print "    arg=" $NF, "etime=" $2}'
echo "  watchdog: $(ps -eo args | awk '/pool_watchdog\.sh --run \/home\/data\/agentmatrix_run / && !/awk/ {c++} END {print c+0}')"
date -Is
