RUN=/home/data/agentmatrix_run
echo "=== 000-014 各分片日志：是否成功、失败原因 ==="
for i in 000 001 002 003 004 005 006 007 008 009 010 011 012 013 014; do
  f="$RUN/logs/shard$i.log"
  if [ ! -f "$f" ]; then echo "  shard$i: 无日志"; continue; fi
  ok=$(grep -c "### shard$i done" "$f" 2>/dev/null || echo 0)
  fail=$(grep -cE "FAILED|Traceback|Error|error:" "$f" 2>/dev/null || echo 0)
  printf "  shard%s  完成标记=%s  错误行=%s  mtime=%s\n" "$i" "$ok" "$fail" "$(stat -c '%y' "$f" | cut -c1-19)"
done

echo
echo "=== shard004 日志尾部 ==="
tail -25 "$RUN/logs/shard004.log" 2>/dev/null
echo
echo "=== shard005 日志尾部 ==="
tail -25 "$RUN/logs/shard005.log" 2>/dev/null

echo
echo "=== 全部分片日志中的失败统计 ==="
grep -lE "BUILD FAILED|TRAIN FAILED|OOS FAILED" "$RUN"/logs/shard*.log 2>/dev/null | sed 's|.*/||' | tr '\n' ' '
echo
echo "  （列出的是含失败标记的日志）"
date -Is
