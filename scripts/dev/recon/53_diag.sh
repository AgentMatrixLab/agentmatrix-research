#!/usr/bin/env bash
echo "=== 诊断：是否在换页抖动 ==="
free -g
swapon --show
echo "负载: $(uptime | sed 's/.*average: //')"
echo "阻塞在 IO 的进程: $(ps -eo stat | grep -c '^D')"
echo
echo "=== 当前 worker 内存 ==="
ps -eo pid,etime,rss,args --sort=-rss | grep -E "[b]uild_factor|[v]alidate-batch" | head -6 | awk '{printf "  pid=%s etime=%s rss=%.1fGB\n", $1, $2, $3/1048576}'
echo
echo "=== 已完成 ==="
echo "  oos 分片: $(ls /home/data/agentmatrix_run/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l)"
echo "  train 分片: $(ls /home/data/agentmatrix_run/shards/shard*/train/batch_manifest.json 2>/dev/null | wc -l)"
echo "  失败: $(grep -l FAILED /home/data/agentmatrix_run/logs/shard*.log 2>/dev/null | wc -l)"
echo
echo "=== 正在跑哪些分片 ==="
for f in $(ls -t /home/data/agentmatrix_run/logs/shard*.log 2>/dev/null | head -4); do
  printf "  %-12s %s\n" "$(basename $f)" "$(tail -1 $f 2>/dev/null | cut -c1-70)"
done
