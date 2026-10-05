#!/usr/bin/env bash
# Stop the current (doomed) run precisely, then relaunch with the provenance fix.
#
# The driver's argv is exactly ["bash", "scripts/dev/run_sharded.sh", "213", "3", ...].
# Matching on argv[2] rather than grepping the whole command line is what keeps this
# from killing the shell that is running it -- a plain pattern match did exactly
# that twice, because the script's own text contains the string being matched.
set -u
RUN=/home/data/agentmatrix_run

echo "=== 停掉旧驱动 ==="
for pid in $(ps -eo pid,args | awk '$2=="bash" && $3 ~ /run_sharded\.sh$/ {print $1}'); do
  echo "  driver $pid"
  kill -TERM "$pid" 2>/dev/null
done
sleep 3
for pid in $(ps -eo pid,args | grep -E "[b]uild_factor_values.py|[v]alidate-batch" | awk '{print $1}'); do
  kill -KILL "$pid" 2>/dev/null
done
sleep 2
echo "  残留: $(ps -eo args | grep -cE '[b]uild_factor|[v]alidate-batch')"

echo
echo "=== 确认修复在位 ==="
cd "$RUN/agentmatrix" || exit 1
echo -n "  COMMIT 文件: "; cat COMMIT 2>/dev/null || echo "(缺失)"
grep -c "AGENTMATRIX_COMMIT" research_core/factor_lab/deterministic_validation.py
echo "  ^ 应 > 0"
python -X utf8 - <<'PYEOF'
import sys
sys.path.insert(0, "/home/data/agentmatrix_run/agentmatrix")
from research_core.factor_lab.deterministic_validation import _git_commit
print("  _git_commit() ->", _git_commit())
PYEOF

echo
echo "=== 清理并重启 ==="
rm -rf "$RUN"/shards/* 2>/dev/null
mkdir -p "$RUN/shards" "$RUN/logs"
rm -f "$RUN"/logs/shard*.log
echo "  磁盘: $(df -h / | awk 'NR==2{print $4}')  内存: $(free -g | awk '/^Mem:/{print $7}')GB"

setsid nohup bash scripts/dev/run_sharded.sh 213 3 2020-01-02 \
    > "$RUN/logs/sharded_driver.log" 2>&1 < /dev/null &
echo "  driver pid=$!"
sleep 30
echo "--- 驱动 ---"
tail -5 "$RUN/logs/sharded_driver.log"
echo "--- 首个分片 ---"
tail -4 "$RUN/logs/shard00.log" 2>/dev/null
free -g | head -2
uptime
