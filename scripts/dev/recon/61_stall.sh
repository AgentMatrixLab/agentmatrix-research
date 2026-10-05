RUN=/home/data/agentmatrix_run
echo "时间: $(date -Is)"
echo "oos 完成: $(ls $RUN/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l)"
echo "train 完成: $(ls $RUN/shards/shard*/train/batch_manifest.json 2>/dev/null | wc -l)"
echo
echo "--- 最近 6 个分片日志 ---"
for f in $(ls -t $RUN/logs/shard*.log 2>/dev/null | head -6); do
  printf "%-16s %s | %s\n" "$(basename $f)" "$(stat -c %y $f | cut -c12-19)" "$(tail -1 $f | cut -c1-60)"
done
echo
echo "--- 004 / 005 的尾部 ---"
for i in 004 005; do
  echo "== shard$i =="
  tail -5 "$RUN/logs/shard$i.log" 2>/dev/null | cut -c1-90
done
echo
echo "--- 进程 ---"
ps -eo pid,etime,rss,args | grep -E "[v]alidate-batch|[b]uild_factor" | awk '{printf "  %s %s %.1fGB\n", $1, $2, $3/1048576}'
free -g | head -2
uptime
