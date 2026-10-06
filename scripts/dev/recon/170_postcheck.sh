RUN=/home/data/agentmatrix_run
echo "=== 交付裁决（应仍为已交付状态）==="
cat "$RUN/logs/auto_deliver.done" 2>/dev/null | sed 's/^/  /'
echo
echo "=== 交付产物是否完好 ==="
for f in delivery_manifest.csv delivery_manifest.summary.json supplementary_report.json \
         cross_check.json README.md strategy_demos/backtest_results.json \
         live_signals/file_orders.csv package/package_manifest.json; do
  p="$RUN/delivery/$f"
  if [ -f "$p" ]; then
    printf "  OK   %-42s %s\n" "$f" "$(stat -c '%y' "$p" | cut -c1-19)"
  else
    printf "  **缺失** %s\n" "$f"
  fi
done
echo "  逐因子证据目录数: $(ls -d $RUN/delivery/package/factors/*/ 2>/dev/null | wc -l)"
echo
echo "=== 交付后作业状态（pool 应已停止，不再产生新分片）==="
echo "  分片完成: $(ls $RUN/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l) （触发时 123）"
echo "  run_pool: $(ps -eo args | awk '/run_pool\.sh/ && !/awk/ {c++} END {print c+0}')   watchdog: $(ps -eo args | awk '/pool_watchdog\.sh --run \/home\/data\/agentmatrix_run / && !/awk/ {c++} END {print c+0}')   auto_deliver: $(ps -eo args | awk '/auto_deliver\.sh --run/ && !/awk/ {c++} END {print c+0}')"
echo "  （三者应为 0 —— 交付后按设计保持停止）"
echo "  仍在跑: $(ps -eo args | awk '/retain_passing|mirror_runtime/ && !/awk/ {c++} END {print c+0}') 个（retain/mirror 无害共存）"
echo
echo "=== 并发 agent 的进程 ==="
n=$(ps -eo args | awk '/rebuild_passing_factors/ && !/awk/ {c++} END {print c+0}')
echo "  rebuild 进程数: $n"
[ "$n" -gt 0 ] && ps -eo etime,args | awk '/rebuild_passing_factors/ && !/awk/ && /python/ {print "    etime=" $1; exit}'
echo "  dryrun 目录: $(du -sh $RUN/delivery_dryrun 2>/dev/null | cut -f1)"
echo
echo "=== 资源 ==="
df -h / | awk 'NR==2{print "  磁盘可用 "$4}'
free -g | awk '/^Mem:/{print "  内存可用 "$7"GB"}'
date -Is
