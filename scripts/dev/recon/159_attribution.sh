RUN=/home/data/agentmatrix_run
echo "=== shard059/060/061/062 的阶段耗时（检验上个缺口是否真由我的彩排造成）==="
for i in 059 060 061 062; do
  f="$RUN/logs/shard$i.log"
  [ -f "$f" ] || { echo "  shard$i: 无日志"; continue; }
  echo "  --- shard$i"
  grep -E 'start |build wall|train wall|oos wall|done ' "$f" 2>/dev/null | sed 's/^/     /'
  echo "     build 速率: $(grep -o '[0-9.]*s/factor' "$f" 2>/dev/null | tail -1)"
done
echo
echo "=== 结论性比较 ==="
/home/data/conda-envs/rqsdk/bin/python -X utf8 - <<'PYEOF'
import re
from datetime import datetime
from pathlib import Path
run = Path("/home/data/agentmatrix_run/logs")
print("  %-8s %-10s %-10s %-10s %-10s" % ("shard", "build", "train", "oos", "总计"))
for i in ("059", "060", "061", "062"):
    text = (run / f"shard{i}.log").read_text(errors="replace") if (run / f"shard{i}.log").is_file() else ""
    def g(pat):
        m = re.search(pat, text)
        return float(m.group(1)) if m else None
    b, t, o = g(r"build wall=([\d.]+)s"), g(r"train wall=([\d.]+)s"), g(r"oos wall=([\d.]+)s")
    if b is None:
        print("  %-8s %-10s %-10s %-10s %-10s" % (i, f"{b:.0f}" if b else "-",
              f"{t:.0f}" if t else "-", f"{o:.0f}" if o else "-", "未完成"))
        continue
    total = (b or 0) + (t or 0) + (o or 0)
    print("  %-8s %-10.0f %-10.0f %-10.0f %-10.0f" % (i, b, t or 0, o or 0, total))
PYEOF
echo
echo "  参考：便宜分片 build≈176s，昂贵分片 build≈1671-1851s"
echo "  缺口 59→60 为 2135s；若 shard060 自身耗时接近该值，则缺口由昂贵分片解释，而非我的彩排"
date -Is
