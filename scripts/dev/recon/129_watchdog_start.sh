RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
echo "=== 清理错误的判断，重新启动（现在用 mkdir 原子锁）==="
rm -rf "$RUN/logs/pool_watchdog.lock" 2>/dev/null
setsid nohup bash "$REPO/scripts/dev/pool_watchdog.sh" --run "$RUN" --total 213 \
  > "$RUN/logs/pool_watchdog.stdout" 2>&1 < /dev/null &
sleep 20
echo
echo "=== 单实例验证：再启一次，应当拒绝 ==="
bash "$REPO/scripts/dev/pool_watchdog.sh" --run "$RUN" --total 213 2>&1 | sed 's/^/  /'
echo
echo "=== watchdog 日志（应显示检测到 pool 在跑）==="
tail -6 "$RUN/logs/pool_watchdog.log" 2>/dev/null | sed 's/^/  /'
echo
echo "=== 进程核对 ==="
echo "  run_pool.sh  : $(ps -eo args | awk '/run_pool\.sh/ && !/awk/ {c++} END {print c+0}')  （必须恰好 1）"
echo "  watchdog     : $(ps -eo args | awk '/bash .*pool_watchdog\.sh/ && !/awk/ {c++} END {print c+0}')  （必须恰好 1）"
echo "  在跑分片     : $(ps -eo args | awk '/run_one_shard\.sh [0-9]/ && !/awk/ {c++} END {print c+0}')"
echo "  oos 完成     : $(ls $RUN/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l) / 213"
echo "  锁内容       : $(cat $RUN/logs/pool_watchdog.lock/pid 2>/dev/null)"
date -Is
