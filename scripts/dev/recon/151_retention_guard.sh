RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
cd $REPO || exit 1
echo "=== 1. 当前留存是否已追上（此前抽检显示差 1）==="
OOS=$(ls $RUN/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l)
PARTS=$(ls $RUN/delivery/values/parts/*.parquet 2>/dev/null | wc -l)
echo "  oos=$OOS parts=$PARTS $([ "$PARTS" -ge "$OOS" ] && echo '已一致（此前是瞬态滞后）' || echo '** 仍滞后 **')"

echo
echo "=== 2. 语法检查 ==="
sed -i 's/\r$//' scripts/dev/auto_deliver.sh
bash -n scripts/dev/auto_deliver.sh && echo "  auto_deliver.sh: bash -n OK"

echo
echo "=== 3. 新的等待逻辑 ==="
grep -n 'waiting for retention\|retention coverage at chain' scripts/dev/auto_deliver.sh | sed 's/^/  /'

echo
echo "=== 4. dry-run 复核（阈值 1 仍应触发；等待逻辑不应死循环）==="
rm -f "$RUN/logs/auto_deliver.log"
timeout 60 bash scripts/dev/auto_deliver.sh --run "$RUN" --threshold 1 --interval 5 --dry-run
echo "  退出码 $?"
grep -E 'retention|DRY RUN|threshold reached' "$RUN/logs/auto_deliver.log" | sed 's/^/    /'

echo
echo "=== 5. 重启以载入（阈值仍 330）==="
OLD=$(ps -eo pid,args | awk '/auto_deliver\.sh --run/ && !/awk/ {print $1; exit}')
[ -n "$OLD" ] && kill -TERM "$OLD" 2>/dev/null && echo "  已停 $OLD"
sleep 3
rm -f "$RUN/logs/auto_deliver.log" "$RUN/logs/auto_deliver.done"
setsid nohup bash "$REPO/scripts/dev/auto_deliver.sh" --run "$RUN" --threshold 330 \
  --total 213 --interval 300 --deadline "2026-10-07 06:00" \
  > "$RUN/logs/auto_deliver.stdout" 2>&1 < /dev/null &
sleep 15
cat "$RUN/logs/auto_deliver.log" 2>/dev/null | sed 's/^/    /'
echo
echo "  生产: pool=$(ps -eo args | awk '/run_pool\.sh/ && !/awk/ && !/auto_deliver/ {c++} END {print c+0}') watchdog=$(ps -eo args | awk '/pool_watchdog\.sh --run \/home\/data\/agentmatrix_run / && !/awk/ {c++} END {print c+0}') auto=$(ps -eo args | awk '/auto_deliver\.sh --run/ && !/awk/ {c++} END {print c+0}')"
date -Is
