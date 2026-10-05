RUN=/home/data/agentmatrix_run
echo "--- 驱动进程 ---"
ps -eo pid,etime,args | grep -E "[r]un_sharded" | cut -c1-100
echo
echo "--- 所有分片日志的 mtime（最近 8 个） ---"
ls -t "$RUN"/logs/shard*.log 2>/dev/null | head -8 | while read f; do
  printf "  %-16s %s  %sB\n" "$(basename "$f")" "$(stat -c %y "$f" | cut -c1-19)" "$(stat -c %s "$f")"
done
echo
echo "--- 每个分片日志最后一行（最近 6 个） ---"
ls -t "$RUN"/logs/shard*.log 2>/dev/null | head -6 | while read f; do
  printf "  %-12s | %s\n" "$(basename "$f")" "$(tail -1 "$f" 2>/dev/null | cut -c1-80)"
done
echo
echo "--- 目录时间 ---"
stat -c '%n %y' "$RUN/shards" "$RUN/logs" 2>/dev/null
echo
echo "--- 当前时间 ---"
date -Is
echo
echo "--- 分片目录中已有文件的分片 ---"
ls -d "$RUN"/shards/shard*/ 2>/dev/null | head -3
for d in $(ls -d "$RUN"/shards/shard*/ 2>/dev/null | head -4); do
  echo "  $d: $(ls "$d" 2>/dev/null | tr '\n' ' ')"
done
