RUN=/home/data/agentmatrix_run
echo "服务器时间: $(date -Is)"
echo "驱动日志行数: $(wc -l < $RUN/logs/sharded_driver.log)"
echo "驱动 started 次数: $(grep -c 'started' $RUN/logs/sharded_driver.log)"
echo
echo "--- 驱动最后 6 行 ---"
tail -6 "$RUN/logs/sharded_driver.log"
echo
echo "--- 所有 shard*.log 的最新 mtime ---"
ls -t "$RUN"/logs/shard*.log 2>/dev/null | head -6 | while read f; do
  printf "  %-14s %s\n" "$(basename "$f")" "$(stat -c %y "$f" | cut -c1-19)"
done
echo
echo "--- 最新分片日志的尾部 ---"
NEWEST=$(ls -t "$RUN"/logs/shard*.log 2>/dev/null | head -1)
echo "  ($NEWEST)"
tail -6 "$NEWEST" 2>/dev/null | cut -c1-100
echo
echo "--- 运行中的相关进程 ---"
ps -eo pid,etime,rss,args | grep -E "[b]uild_factor|[v]alidate-batch|[r]un_sharded" | cut -c1-95
echo
echo "--- 完成计数 ---"
echo "  train: $(ls $RUN/shards/shard*/train/batch_manifest.json 2>/dev/null | wc -l)"
echo "  oos  : $(ls $RUN/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l)"
echo "  失败: $(grep -l 'FAILED' $RUN/logs/shard*.log 2>/dev/null | wc -l)"
echo
free -g | head -2
uptime
