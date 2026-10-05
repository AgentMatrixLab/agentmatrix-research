RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
echo "=== 1. pkill 只出现在注释里（确认它绝不杀进程）==="
grep -n 'pkill\|kill' "$REPO/scripts/dev/pool_watchdog.sh" | sed 's/^/  /'
echo
echo "=== 2. 启动 watchdog（detached）==="
if pgrep -f 'pool_watchdog.sh' > /dev/null 2>&1; then
  echo "  已在运行，不重复启动"
else
  setsid nohup bash "$REPO/scripts/dev/pool_watchdog.sh" --run "$RUN" --total 213 \
    > "$RUN/logs/pool_watchdog.stdout" 2>&1 < /dev/null &
  echo "  已启动 pid=$!"
fi
sleep 45
echo
echo "=== 3. watchdog 日志（应显示它检测到 pool 在跑、不去抢）==="
cat "$RUN/logs/pool_watchdog.log" 2>/dev/null | tail -8 | sed 's/^/  /'
echo
echo "=== 4. 当前 pool 状态（应只有一个 pool）==="
echo "  run_pool.sh 进程数: $(ps -eo args | awk '/run_pool\.sh/ && !/awk/ {c++} END {print c+0}')"
echo "  在跑分片: $(ps -eo args | awk '/run_one_shard\.sh [0-9]/ && !/awk/ {c++} END {print c+0}')"
echo "  watchdog 进程数: $(ps -eo args | awk '/pool_watchdog\.sh/ && !/awk/ {c++} END {print c+0}')"
echo "  oos 完成: $(ls $RUN/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l) / 213"
date -Is
