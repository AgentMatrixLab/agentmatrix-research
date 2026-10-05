#!/usr/bin/env bash
set -u
RUN=/home/data/agentmatrix_run

echo "=== 停掉串行的旧驱动 ==="
for pid in $(ps -eo pid,args | awk '$2=="bash" && $3 ~ /run_sharded\.sh$/ {print $1}'); do
  echo "  driver $pid"; kill -TERM "$pid" 2>/dev/null
done
sleep 3
for pid in $(ps -eo pid,args | grep -E "[b]uild_factor_values.py|[v]alidate-batch" | awk '{print $1}'); do
  kill -KILL "$pid" 2>/dev/null
done
sleep 2
echo "  残留: $(ps -eo args | grep -cE '[b]uild_factor|[v]alidate-batch')"
echo "  已完成 oos 分片: $(ls $RUN/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l)"

cd "$RUN/agentmatrix" || exit 1
sed -i 's/\r$//' scripts/dev/run_one_shard.sh scripts/dev/run_pool.sh
chmod +x scripts/dev/run_one_shard.sh scripts/dev/run_pool.sh

echo
echo "=== 启动 worker pool ==="
setsid nohup bash scripts/dev/run_pool.sh 213 3 > "$RUN/logs/pool_driver.log" 2>&1 < /dev/null &
echo "  pool pid=$!"
sleep 40
echo "--- pool 日志 ---"
cat "$RUN/logs/pool_driver.log"
echo "--- 运行中的 worker ---"
ps -eo pid,etime,rss,args | grep -E "[b]uild_factor|[v]alidate-batch" | awk '{printf "  pid=%s etime=%s rss=%.1fGB\n", $1, $2, $4/1048576}'
echo "--- 资源 ---"
free -g | head -2
uptime
date -Is
