RUN=/home/data/agentmatrix_run
echo "=== 占用率采样结果 ==="
tail -12 "$RUN/rehearsal/occupancy.log" 2>/dev/null
echo
echo "=== 最近分片的阶段耗时（/usr/bin/time）==="
for i in 019 020 021 022 023 024; do
  f="$RUN/logs/shard$i.log"
  [ -f "$f" ] || { echo "  shard$i: 无日志"; continue; }
  echo "  --- shard$i"
  grep -E 'start |build wall|train wall|oos wall|FAILED|signal|done ' "$f" | sed 's/^/     /'
done
echo
echo "=== shard023 日志尾部（看是否在等锁）==="
tail -8 "$RUN/logs/shard023.log" 2>/dev/null
echo
echo "=== 当前进程与锁 ==="
ps -eo pid,etime,rss,args | awk '/validate-batch|build_factor_values|run_one_shard/ && !/awk/ {printf "  %.1fGB etime=%s %s\n", $3/1048576, $2, substr($0, index($0,$4), 90)}'
echo
echo "  锁文件: $(ls -la $RUN/logs/oos.lock 2>/dev/null)"
echo "  谁持有: $(command -v fuser >/dev/null && fuser $RUN/logs/oos.lock 2>&1 || echo 'fuser 不可用')"
date -Is
