RUN=/home/data/agentmatrix_run
echo "--- 驱动 ---"
tail -8 $RUN/logs/sharded_driver.log
echo
echo "--- 各分片日志尾部 ---"
for f in $RUN/logs/shard*.log; do
  [ -f "$f" ] || continue
  name=$(basename "$f" .log)
  last=$(tail -1 "$f" 2>/dev/null | cut -c1-80)
  size=$(stat -c %s "$f" 2>/dev/null)
  printf "  %-10s %6sB  %s\n" "$name" "$size" "$last"
done
echo
echo "--- 运行中的 python ---"
ps -eo pid,rss,etime,args | grep -E "build_factor|validate" | grep -v grep | cut -c1-100
echo
echo "--- 内存 ---"
free -g | head -2
echo "--- 磁盘 ---"
df -h / | tail -1
echo "--- 各片产物 ---"
du -sh $RUN/shards/* 2>/dev/null | head -20
echo
echo "--- OOM 检查（最近） ---"
dmesg -T 2>/dev/null | grep -i "killed process" | tail -3
