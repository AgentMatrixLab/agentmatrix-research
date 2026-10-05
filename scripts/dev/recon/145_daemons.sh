RUN=/home/data/agentmatrix_run
echo "=== 守护进程一览 ==="
ps -eo pid,etime,args | grep -E 'run_pool\.sh|pool_watchdog\.sh --run|auto_deliver\.sh --run|retain_passing|mirror_runtime' | grep -v grep | cut -c1-100 | sed 's/^/  /'
echo
echo "=== auto_deliver 最近决策 ==="
tail -2 "$RUN/logs/auto_deliver.log" 2>/dev/null | sed 's/^/  /'
echo
echo "=== 关键计数 ==="
echo "  oos 完成: $(ls $RUN/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l) / 213"
echo "  parts   : $(ls $RUN/delivery/values/parts/*.parquet 2>/dev/null | wc -l)"
date -Is
