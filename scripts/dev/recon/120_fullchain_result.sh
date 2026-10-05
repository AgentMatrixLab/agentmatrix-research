RUN=/home/data/agentmatrix_run
echo "=== 链日志：各步骤标题与关键行 ==="
grep -E '^#{4,}|^  wall=|wall=|exit=|FAILED|WARNING|IN DELIVERY|交付|发现数|error|Error|Traceback' \
  "$RUN/rehearsal/fullchain.log" 2>/dev/null | grep -vE 's/factor|neutral-IC' | head -60
echo
echo "=== 日志尾部 ==="
tail -25 "$RUN/rehearsal/fullchain.log" 2>/dev/null
echo
echo "=== 链产物 ==="
ls -la "$RUN/delivery" 2>/dev/null
echo
echo "=== pool 是否已重启 ==="
ps -eo pid,etime,args | awk '/run_pool|run_one_shard\.sh [0-9]/ && !/awk/ {print "  " $1, $2, substr($0, index($0,$3), 70)}'
echo "  oos 完成: $(ls $RUN/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l) / 213"
echo "  内存可用: $(free -g | awk '/^Mem:/{print $7}')GB"
date -Is
