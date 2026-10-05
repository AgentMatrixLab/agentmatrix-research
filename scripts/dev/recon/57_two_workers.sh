#!/usr/bin/env bash
# Drop to 2 workers. Three validation processes at ~20 GB each plus the other
# tenants on this box exceeds 62 GB, and the box starts swapping -- measured again:
# 54/62 GB used, sshd unresponsive, load 10.
set -u
RUN=/home/data/agentmatrix_run
cd "$RUN/agentmatrix" || exit 1

echo "=== 停掉 3 路 pool ==="
for pid in $(ps -eo pid,args | awk '$2=="bash" && $3 ~ /run_pool\.sh$/ {print $1}'); do kill -TERM "$pid" 2>/dev/null; done
sleep 2
for pid in $(ps -eo pid,args | grep -E "[x]args|[r]un_one_shard|[b]uild_factor_values.py|[v]alidate-batch" | awk '{print $1}'); do
  kill -KILL "$pid" 2>/dev/null
done
sleep 3
echo "  残留: $(ps -eo args | grep -cE '[b]uild_factor|[v]alidate-batch')"

echo
echo "=== 已完成情况（会保留） ==="
echo "  oos 分片: $(ls $RUN/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l)"
echo "  train 分片: $(ls $RUN/shards/shard*/train/batch_manifest.json 2>/dev/null | wc -l)"
free -g | head -2

echo
echo "=== 以 2 路重启（跳过已有结果的分片） ==="
setsid nohup bash scripts/dev/run_pool.sh 213 2 > "$RUN/logs/pool_driver.log" 2>&1 < /dev/null &
echo "  pool pid=$!"
sleep 40
cat "$RUN/logs/pool_driver.log"
echo "--- worker ---"
ps -eo pid,etime,rss,args | grep -E "[b]uild_factor|[v]alidate-batch" | awk '{printf "  %s %s %.1fGB\n", $1, $2, $3/1048576}'
free -g | head -2
uptime
