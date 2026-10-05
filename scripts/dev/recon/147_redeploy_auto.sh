RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
echo "=== 1. 服务器端语法检查 ==="
cd $REPO || exit 1
for f in scripts/dev/auto_deliver.sh scripts/dev/stop_and_deliver.sh; do
  sed -i 's/\r$//' "$f"
  bash -n "$f" && echo "  $f: bash -n OK" || echo "  $f: ** 语法错误 **"
done

echo
echo "=== 2. auto_deliver 里的验收检查行 ==="
grep -n 'verify_delivery\|acceptance' scripts/dev/auto_deliver.sh | sed 's/^/  /'

echo
echo "=== 3. 只有一处 delivered 计数逻辑（确认没有重复块）==="
echo "  delivered= 出现次数: $(grep -c 'delivered=\$(' scripts/dev/auto_deliver.sh)"
echo "  DONE_MARK 写入次数 : $(grep -c '> \"\$DONE_MARK\"' scripts/dev/auto_deliver.sh)"

echo
echo "=== 4. dry-run 复核（阈值 1 应触发且不碰生产）==="
rm -f "$RUN/logs/auto_deliver.log"
timeout 20 bash scripts/dev/auto_deliver.sh --run "$RUN" --threshold 1 --interval 5 --dry-run
tail -2 "$RUN/logs/auto_deliver.log" | sed 's/^/  /'

echo
echo "=== 5. 重启 auto_deliver 以载入新版本 ==="
OLD=$(ps -eo pid,args | awk '/auto_deliver\.sh --run/ && !/awk/ {print $1; exit}')
[ -n "$OLD" ] && kill -TERM "$OLD" 2>/dev/null && echo "  已停旧实例 $OLD"
sleep 3
rm -f "$RUN/logs/auto_deliver.log" "$RUN/logs/auto_deliver.done"
setsid nohup bash "$REPO/scripts/dev/auto_deliver.sh" --run "$RUN" --threshold 308 \
  --total 213 --interval 300 --deadline "2026-10-07 06:00" \
  > "$RUN/logs/auto_deliver.stdout" 2>&1 < /dev/null &
sleep 15
echo "  --- 新实例日志 ---"
cat "$RUN/logs/auto_deliver.log" 2>/dev/null | sed 's/^/    /'

echo
echo "=== 6. 生产核对 ==="
echo "  run_pool.sh : $(ps -eo args | awk '/run_pool\.sh/ && !/awk/ && !/auto_deliver/ {c++} END {print c+0}')"
echo "  watchdog    : $(ps -eo args | awk '/pool_watchdog\.sh --run \/home\/data\/agentmatrix_run / && !/awk/ {c++} END {print c+0}')"
echo "  auto_deliver: $(ps -eo args | awk '/auto_deliver\.sh --run/ && !/awk/ {c++} END {print c+0}')（必须为 1）"
echo "  在跑分片    : $(ps -eo args | awk '/run_one_shard\.sh [0-9]/ && !/awk/ {c++} END {print c+0}')"
echo "  oos 完成    : $(ls $RUN/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l) / 213"
date -Is
