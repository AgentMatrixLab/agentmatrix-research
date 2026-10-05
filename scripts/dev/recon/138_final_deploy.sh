REPO=/home/data/agentmatrix_run/agentmatrix
cd $REPO || exit 1
sed -i 's/\r$//' scripts/dev/stop_and_deliver.sh
bash -n scripts/dev/stop_and_deliver.sh && echo "bash -n OK"
echo
echo "=== 步骤顺序（应为 1,2,3,4,5,6 无重复）==="
grep -n '^echo "===' scripts/dev/stop_and_deliver.sh | sed 's/^/  /'
echo
echo "=== 关键顺序核对：watchdog 必须在 pool 之前停 ==="
echo "  停 watchdog 的行号: $(grep -n '停止 watchdog pid' scripts/dev/stop_and_deliver.sh | cut -d: -f1)"
echo "  停 pool 的行号    : $(grep -n '停止 pool（按进程组）' scripts/dev/stop_and_deliver.sh | cut -d: -f1)"
echo
echo "=== 生产核对 ==="
RUN=/home/data/agentmatrix_run
echo "  watchdog 进程数: $(ps -eo args | awk '/pool_watchdog\.sh --run \/home\/data\/agentmatrix_run / && !/awk/ {c++} END {print c+0}')（应为 1）"
echo "  run_pool.sh    : $(ps -eo args | awk '/run_pool\.sh/ && !/awk/ {c++} END {print c+0}')（应为 1）"
echo "  在跑分片       : $(ps -eo args | awk '/run_one_shard\.sh [0-9]/ && !/awk/ {c++} END {print c+0}')"
echo "  oos 完成       : $(ls $RUN/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l) / 213"
echo "  watchdog 日志  :"
tail -2 $RUN/logs/pool_watchdog.log | sed 's/^/    /'
date -Is
