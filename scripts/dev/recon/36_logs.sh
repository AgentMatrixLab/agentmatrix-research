echo "===== 日志时间戳（区分新旧） ====="
for f in /home/data/agentmatrix_run/logs/shard0[0-9].log; do
  [ -f "$f" ] || continue
  printf "  %-12s mtime=%s  size=%s\n" "$(basename $f)" "$(stat -c %y "$f" | cut -c1-19)" "$(stat -c %s "$f")"
done
echo
echo "===== shard00 内容 ====="
cat /home/data/agentmatrix_run/logs/shard00.log
echo
echo "===== 最新日志（按时间） ====="
ls -t /home/data/agentmatrix_run/logs/shard*.log 2>/dev/null | head -4
echo
echo "===== 当前时间 ====="
date -Is
echo
echo "===== 本次驱动启动时间 ====="
head -3 /home/data/agentmatrix_run/logs/sharded_driver.log
