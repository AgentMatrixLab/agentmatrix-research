RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
echo "=== 1. 语法与关键安全点核对 ==="
bash -n "$REPO/scripts/dev/auto_deliver.sh" && echo "  bash -n OK"
echo "  pkill 出现次数: $(grep -c pkill "$REPO/scripts/dev/auto_deliver.sh")（应仅在注释里）"
echo "  rm -rf 的目标:"
grep -o 'rm -rf [^ ]*' "$REPO/scripts/dev/auto_deliver.sh" | sed 's/^/    /'
echo "  顺序核对（watchdog 必须先于 pool）:"
echo "    停 watchdog 行号: $(grep -n 'watchdog stopped' "$REPO/scripts/dev/auto_deliver.sh" | cut -d: -f1)"
echo "    停 pool 行号    : $(grep -n 'pool stopped' "$REPO/scripts/dev/auto_deliver.sh" | cut -d: -f1)"

echo
echo "=== 2. dry-run 验证触发路径（不许碰生产）==="
rm -f "$RUN/logs/auto_deliver.log" "$RUN/logs/auto_deliver.done"
timeout 30 bash "$REPO/scripts/dev/auto_deliver.sh" --run "$RUN" --threshold 1 --interval 5 --dry-run
echo "  退出码 $?"
echo "  --- 日志 ---"
cat "$RUN/logs/auto_deliver.log" 2>/dev/null | sed 's/^/    /'

echo
echo "=== 3. 用真实阈值试跑一次（应看到 81 个通过、不触发）==="
rm -f "$RUN/logs/auto_deliver.log"
timeout 20 bash "$REPO/scripts/dev/auto_deliver.sh" --run "$RUN" --threshold 308 --interval 5 --dry-run
echo "  --- 日志 ---"
cat "$RUN/logs/auto_deliver.log" 2>/dev/null | sed 's/^/    /'

echo
echo "=== 4. 生产未被触碰 ==="
echo "  run_pool.sh: $(ps -eo args | awk '/run_pool\.sh/ && !/awk/ && !/auto_deliver/ {c++} END {print c+0}')"
echo "  watchdog   : $(ps -eo args | awk '/pool_watchdog\.sh --run \/home\/data\/agentmatrix_run / && !/awk/ {c++} END {print c+0}')"
echo "  oos 完成   : $(ls $RUN/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l) / 213"
date -Is
