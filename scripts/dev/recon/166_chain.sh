RUN=/home/data/agentmatrix_run
echo "=== 链进度（步骤标题与耗时）==="
grep -E '^#{4,}|FAILED|wall=|WARNING' "$RUN/logs/auto_deliver_chain.log" 2>/dev/null | tail -16 | sed 's/^/  /'
echo
echo "=== 判定标记是否已写出 ==="
if [ -f "$RUN/logs/auto_deliver.done" ]; then
  echo "  ** 已完成 ** $(cat "$RUN/logs/auto_deliver.done")"
else
  echo "  未完成（链仍在跑或刚落盘）"
fi
echo
echo "=== 资源 ==="
free -g | awk '/^Mem:/{print "  内存可用 " $7 "GB"}'
df -h / | awk 'NR==2{print "  磁盘可用 " $4}'
echo "  在跑重负载进程:"
ps -eo pcpu,etime,rss,args --sort=-pcpu | awk 'NR<=4' | cut -c1-105 | sed 's/^/    /'
echo
echo "=== auto_deliver 日志尾 ==="
tail -4 "$RUN/logs/auto_deliver.log" 2>/dev/null | sed 's/^/  /'
date -Is
