#!/usr/bin/env bash
set -u
RUN=/home/data/agentmatrix_run
cd "$RUN/agentmatrix" || exit 1

echo "=== 停掉 pool 与 worker ==="
for pid in $(ps -eo pid,args | awk '$2=="bash" && ($3 ~ /run_pool\.sh$/ || $3 ~ /run_one_shard\.sh$/) {print $1}'); do
  kill -TERM "$pid" 2>/dev/null
done
sleep 2
for pid in $(ps -eo pid,args | grep -E "[b]uild_factor_values.py|[v]alidate-batch|[x]args" | awk '{print $1}'); do
  kill -KILL "$pid" 2>/dev/null
done
sleep 2
echo "  残留: $(ps -eo args | grep -cE '[b]uild_factor|[v]alidate-batch')"

echo
echo "=== 彻底清空分片目录（避免新旧命名混在一起） ==="
echo "  清前: $(ls -d $RUN/shards/shard* 2>/dev/null | wc -l) 个目录"
rm -rf "$RUN"/shards
mkdir -p "$RUN/shards"
rm -f "$RUN"/logs/shard*.log "$RUN"/logs/todo.txt
echo "  清后: $(ls -d $RUN/shards/shard* 2>/dev/null | wc -l) 个目录"
echo "  磁盘: $(df -h / | awk 'NR==2{print $4}')"

echo
echo "=== 启动 pool（213 片，3 并行） ==="
setsid nohup bash scripts/dev/run_pool.sh 213 3 > "$RUN/logs/pool_driver.log" 2>&1 < /dev/null &
echo "  pool pid=$!"
sleep 45
echo "--- pool 日志 ---"
cat "$RUN/logs/pool_driver.log"
echo "--- worker 数 ---"
ps -eo args | grep -c "[b]uild_factor_values.py"
echo "--- 资源 ---"
free -g | head -2
uptime
date -Is
