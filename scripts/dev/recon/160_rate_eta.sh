RUN=/home/data/agentmatrix_run
/home/data/conda-envs/rqsdk/bin/python -X utf8 - <<'PYEOF'
import re
from datetime import datetime
from pathlib import Path

logs = Path("/home/data/agentmatrix_run/logs")
rows = []
for path in logs.glob("shard*.log"):
    text = path.read_text(errors="replace")
    m = re.search(r"### shard\d+ done ([0-9T:+\-]+)", text)
    if not m:
        continue
    rows.append((datetime.fromisoformat(m.group(1)), path.stem))
rows.sort()
print("  完成分片总数:", len(rows))

def rate(window):
    sel = rows[-(window + 1):]
    span = (sel[-1][0] - sel[0][0]).total_seconds() / 3600
    return (len(sel) - 1) / span, span

for w in (10, 20, 30):
    if len(rows) > w:
        r, span = rate(w)
        print("  最近 %2d 个分片: %.1f 片/小时（跨度 %.1f h）" % (w, r, span))

# 昂贵分片的占比：build > 1000s
expensive = 0
total = 0
for path in logs.glob("shard*.log"):
    text = path.read_text(errors="replace")
    m = re.search(r"build wall=([\d.]+)s", text)
    if not m:
        continue
    total += 1
    if float(m.group(1)) > 1000:
        expensive += 1
print()
print("  build 超过 1000s 的分片: %d / %d (%.0f%%)" % (expensive, total, 100 * expensive / total))

# ETA：按最近 20 个的速率
r20, _ = rate(20)
need_shards = 141 - len(rows)
print()
print("  达到 330 个通过需约 141 片（过闸率 58.5%%，每片 4 个）")
print("  当前 %d 片，还需约 %d 片" % (len(rows), need_shards))
hours = need_shards / r20
last = rows[-1][0]
from datetime import timedelta
print("  按最近 20 个的速率 %.1f 片/小时 → %.1f 小时" % (r20, hours))
print("  ⇒ 触发约 %s" % (last + timedelta(hours=hours)).strftime("%m-%d %H:%M"))
print("  ⇒ 加约 40 分钟链 → 交付约 %s" % (last + timedelta(hours=hours, minutes=40)).strftime("%m-%d %H:%M"))
print("  （兜底阀门 10-07 06:00）")
PYEOF
date -Is
