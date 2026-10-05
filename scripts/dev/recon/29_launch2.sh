#!/usr/bin/env bash
set -u
RUN=/home/data/agentmatrix_run
SHARDS=${1:-16}
PARALLEL=${2:-8}
LOG=$RUN/logs/sharded_driver.log
mkdir -p "$RUN/logs"

# 清掉试跑产物，腾磁盘
rm -rf "$RUN/pilot" "$RUN/tiny" "$RUN/shards"

cd "$RUN/agentmatrix" || exit 1
setsid nohup bash "$RUN/agentmatrix/scripts/dev/run_sharded.sh" "$SHARDS" "$PARALLEL" \
    > "$LOG" 2>&1 < /dev/null &
echo "driver pid=$!"
sleep 20
echo "--- 驱动日志 ---"
head -30 "$LOG" 2>/dev/null
echo "--- 磁盘 ---"
df -h / | tail -1
echo "--- 内存 ---"
free -g | head -2
