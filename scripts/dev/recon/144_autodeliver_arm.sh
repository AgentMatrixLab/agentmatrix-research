RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
echo "=== 1. 语法 + dry-run 复核（含 deadline 分支）==="
bash -n "$REPO/scripts/dev/auto_deliver.sh" && echo "  bash -n OK"
rm -f "$RUN/logs/auto_deliver.log"
echo "  --- 阈值 1 应触发 ---"
timeout 20 bash "$REPO/scripts/dev/auto_deliver.sh" --run "$RUN" --threshold 1 --interval 5 --dry-run
grep -c 'DRY RUN' "$RUN/logs/auto_deliver.log" | sed 's/^/    DRY RUN 行数: /'
rm -f "$RUN/logs/auto_deliver.log"
echo "  --- deadline 已过应触发（模拟 2020 年截止）---"
timeout 20 bash "$REPO/scripts/dev/auto_deliver.sh" --run "$RUN" --threshold 99999 --interval 5 --deadline "2020-01-01 00:00" --dry-run
grep -E 'deadline|DRY RUN' "$RUN/logs/auto_deliver.log" | sed 's/^/    /'
rm -f "$RUN/logs/auto_deliver.log"
echo "  --- 真实参数不应触发 ---"
timeout 12 bash "$REPO/scripts/dev/auto_deliver.sh" --run "$RUN" --threshold 308 --interval 5 --dry-run
grep -c 'DRY RUN' "$RUN/logs/auto_deliver.log" | sed 's/^/    DRY RUN 行数（应为 0）: /'

echo
echo "=== 2. 启动真正的自动交付（阈值 308，截止 10-07 06:00）==="
rm -f "$RUN/logs/auto_deliver.log" "$RUN/logs/auto_deliver.done"
setsid nohup bash "$REPO/scripts/dev/auto_deliver.sh" --run "$RUN" --threshold 308 \
  --total 213 --interval 300 --deadline "2026-10-07 06:00" \
  > "$RUN/logs/auto_deliver.stdout" 2>&1 < /dev/null &
sleep 20
echo "  --- 日志 ---"
cat "$RUN/logs/auto_deliver.log" 2>/dev/null | sed 's/^/    /'
echo "  --- 进程 ---"
ps -eo pid,etime,args | awk '/auto_deliver\.sh/ && !/awk/ {print "    " $1, $2, substr($0, index($0,$3), 80)}'

echo
echo "=== 3. 生产核对（pool 与 watchdog 必须都还在）==="
echo "  run_pool.sh: $(ps -eo args | awk '/run_pool\.sh/ && !/awk/ && !/auto_deliver/ {c++} END {print c+0}')"
echo "  watchdog   : $(ps -eo args | awk '/pool_watchdog\.sh --run \/home\/data\/agentmatrix_run / && !/awk/ {c++} END {print c+0}')"
echo "  auto_deliver: $(ps -eo args | awk '/auto_deliver\.sh --run/ && !/awk/ {c++} END {print c+0}')"
echo "  在跑分片   : $(ps -eo args | awk '/run_one_shard\.sh [0-9]/ && !/awk/ {c++} END {print c+0}')"
echo "  oos 完成   : $(ls $RUN/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l) / 213"
date -Is
