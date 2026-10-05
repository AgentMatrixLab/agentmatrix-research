#!/usr/bin/env bash
# Launch the sharded run detached, so it survives the SSH session ending.
set -u
RUN=/home/data/agentmatrix_run
SHARDS=${1:-16}
PARALLEL=${2:-4}
LOG=$RUN/logs/sharded_driver.log
mkdir -p "$RUN/logs"

cd "$RUN/agentmatrix" || exit 1
setsid nohup bash "$RUN/agentmatrix/scripts/dev/run_sharded.sh" "$SHARDS" "$PARALLEL" \
    > "$LOG" 2>&1 < /dev/null &
echo "driver pid=$!"
sleep 5
echo "--- 前 20 行 ---"
head -20 "$LOG" 2>/dev/null
