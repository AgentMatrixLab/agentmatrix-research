#!/usr/bin/env bash
# Launch sized to the measured footprint: 13.5 GB peak per 4-factor shard, ~50 GB
# usable on a box shared with ClickHouse, hermes and other tenants -> 3 workers.
#
# Earlier attempts used 53-factor and 16-factor shards and 6 workers, all sized
# from an assumption that memory scaled with the shard. It does not; it scales with
# rows loaded, and the loader peak is 13.5 GB for 92M rows.
set -u
RUN=/home/data/agentmatrix_run
SHARDS=${1:-213}
PARALLEL=${2:-3}
LOG=$RUN/logs/sharded_driver.log
mkdir -p "$RUN/logs" "$RUN/shards"

echo "=== 清理上一轮 ==="
# Exclude this process and its ancestors. An earlier version of this used a plain
# pattern match and killed its own shell, because the script's own command line
# contains the very string it was grepping for.
SELF=$$
for pid in $(ps -eo pid,args | grep -E "[b]uild_factor_values.py|[v]alidate-batch" | awk '{print $1}'); do
  [ "$pid" = "$SELF" ] && continue
  kill -KILL "$pid" 2>/dev/null
done
echo "  (driver 若在跑则保留，由它自己收尾)"
sleep 2
rm -rf "$RUN"/shards/* "$RUN"/memtest "$RUN"/tiny "$RUN"/pilot 2>/dev/null
mkdir -p "$RUN/shards"
echo "  磁盘可用: $(df -h / | awk 'NR==2{print $4}')"
echo "  内存可用: $(free -g | awk '/^Mem:/{print $7}')GB"
echo "  负载    : $(uptime | sed 's/.*average: //' | cut -d, -f1)"

cd "$RUN/agentmatrix" || exit 1
sed -i 's/\r$//' scripts/dev/run_sharded.sh 2>/dev/null
setsid nohup bash scripts/dev/run_sharded.sh "$SHARDS" "$PARALLEL" 2020-01-02 \
    > "$LOG" 2>&1 < /dev/null &
echo "driver pid=$!"
sleep 25
echo "--- 驱动日志 ---"
tail -12 "$LOG"
echo "--- 资源 ---"
free -g | head -2
uptime
