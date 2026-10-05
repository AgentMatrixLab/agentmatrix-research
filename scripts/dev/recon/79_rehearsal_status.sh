RUN=/home/data/agentmatrix_run
echo "=== 彩排目录 ==="
ls -la $RUN/rehearsal/ 2>/dev/null
echo
echo "=== 彩排进程 ==="
ps -eo pid,etime,rss,args | awk '/consolidate_factor_values|run_robustness_supplement|build_delivery_manifest|build_strategy_demos|build_live_signals|merge_batch/ && !/awk/ {printf "  pid=%s etime=%s rss=%.1fGB\n     %s\n", $1, $2, $4/1048576, substr($0, index($0,$5), 120)}'
echo
echo "=== pool 进度 ==="
echo "  oos 完成: $(ls $RUN/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l) / 213"
echo "  parts   : $(ls $RUN/delivery/values/parts/*.parquet 2>/dev/null | wc -l)"
ps -eo pid,etime,args | awk '/run_one_shard\.sh [0-9]/ {print "    pid=" $1, "etime=" $2, "arg=" $NF}'
echo
echo "=== 温度检查：内存/磁盘 ==="
free -g | head -2
df -h / | awk 'NR==2{print "  磁盘可用: "$4" / "$2}'
echo
echo "=== 最近 retain 日志 ==="
tail -4 $RUN/logs/retain_daemon.log 2>/dev/null
date -Is
