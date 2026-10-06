RUN=/home/data/agentmatrix_run
echo "=== 在跑的分片与阶段 ==="
ps -eo pid,etime,args | awk '/run_one_shard\.sh [0-9]/ {print "  arg=" $NF, "etime=" $2}' | sort -u
echo
echo "=== 在跑的 python 进程（看处在哪个阶段）==="
ps -eo pid,etime,rss,args --sort=-rss | awk '/build_factor_values|validate-batch/ && !/awk/ {printf "  %.1fGB etime=%-8s %s\n", $3/1048576, $2, substr($0, index($0,$4), 95)}'
echo
echo "=== 最近完成的分片 ==="
for f in "$RUN"/logs/shard06*.log; do
  tag=$(basename "$f" .log)
  d=$(grep -o '### shard[0-9]* done [0-9T:+-]*' "$f" 2>/dev/null | head -1 | awk '{print $4}')
  [ -n "$d" ] && echo "  $tag done $d"
done | tail -5
echo
echo "=== 在跑分片的日志尾部（看进度）==="
for i in 062 063; do
  f="$RUN/logs/shard$i.log"
  if [ -f "$f" ]; then
    echo "  --- shard$i (最后 4 行非进度行) ---"
    grep -v 's/factor' "$f" 2>/dev/null | tail -4 | sed 's/^/     /'
    echo "     build 进度行: $(grep -o '[0-9]*/[0-9]*  [0-9.]*s/factor[^|]*' "$f" 2>/dev/null | tail -1)"
  else
    echo "  --- shard$i: 无日志（尚未启动）"
  fi
done
echo
echo "=== 内存 / CPU ==="
free -g | awk '/^Mem:/{printf "  可用 %sGB\n", $7}'
uptime | sed 's/^/  /'
date -Is
