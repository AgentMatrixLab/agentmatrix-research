RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
cd $REPO || exit 1
echo "=== 1. 语法 + 结构（验收块只应出现一次，且在 DONE_MARK 之前）==="
sed -i 's/\r$//' scripts/dev/auto_deliver.sh
bash -n scripts/dev/auto_deliver.sh && echo "  bash -n OK"
echo "  verify_delivery 调用次数: $(grep -c 'verify_delivery.py' scripts/dev/auto_deliver.sh)（应为 1）"
echo "  行号: 验收=$((grep -n 'acceptance=\$?' scripts/dev/auto_deliver.sh | cut -d: -f1))  DONE_MARK=$((grep -n 'DONE_MARK$' scripts/dev/auto_deliver.sh | head -1 | cut -d: -f1))"
grep -n 'acceptance=\$?\|> "\$DONE_MARK"' scripts/dev/auto_deliver.sh | sed 's/^/    /'

echo
echo "=== 2. dry-run 复核 ==="
rm -f "$RUN/logs/auto_deliver.log"
timeout 40 bash scripts/dev/auto_deliver.sh --run "$RUN" --threshold 1 --interval 5 --dry-run
grep -E 'threshold reached|retention coverage|DRY RUN' "$RUN/logs/auto_deliver.log" | sed 's/^/    /'

echo
echo "=== 3. 重启（阈值 330）==="
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
echo "=== 4. 生产核对 ==="
echo "  pool=$(ps -eo args | awk '/run_pool\.sh/ && !/awk/ && !/auto_deliver/ {c++} END {print c+0}') watchdog=$(ps -eo args | awk '/pool_watchdog\.sh --run \/home\/data\/agentmatrix_run / && !/awk/ {c++} END {print c+0}') auto=$(ps -eo args | awk '/auto_deliver\.sh --run/ && !/awk/ {c++} END {print c+0}')"
echo "  阈值: $(grep -o 'threshold=[0-9]*' "$RUN/logs/auto_deliver.log" | head -1)"
date -Is
