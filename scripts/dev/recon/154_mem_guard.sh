RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
cd $REPO || exit 1
echo "=== 1. 语法 + 新守护块 ==="
sed -i 's/\r$//' scripts/dev/auto_deliver.sh
bash -n scripts/dev/auto_deliver.sh && echo "  bash -n OK"
grep -n 'MIN_FREE_GB\|waiting for memory\|starting the chain with' scripts/dev/auto_deliver.sh | sed 's/^/  /'

echo
echo "=== 2. 当前内存与阈值的关系 ==="
free -g | awk '/^Mem:/{printf "  可用 %sGB，阈值 30GB → %s\n", $7, ($7>=30 ? "当前即可直接开链" : "会先等待")}'

echo
echo "=== 3. dry-run：走到内存检查前应不触发实际动作 ==="
rm -f "$RUN/logs/auto_deliver.log"
timeout 40 bash scripts/dev/auto_deliver.sh --run "$RUN" --threshold 1 --interval 5 --dry-run
grep -E 'threshold reached|retention coverage|DRY RUN' "$RUN/logs/auto_deliver.log" | sed 's/^/  /'

echo
echo "=== 4. 重启（阈值 330）==="
OLD=$(ps -eo pid,args | awk '/auto_deliver\.sh --run/ && !/awk/ {print $1; exit}')
[ -n "$OLD" ] && kill -TERM "$OLD" 2>/dev/null && echo "  已停 $OLD"
sleep 3
rm -f "$RUN/logs/auto_deliver.log" "$RUN/logs/auto_deliver.done"
setsid nohup bash "$REPO/scripts/dev/auto_deliver.sh" --run "$RUN" --threshold 330 \
  --total 213 --interval 300 --deadline "2026-10-07 06:00" \
  > "$RUN/logs/auto_deliver.stdout" 2>&1 < /dev/null &
sleep 15
cat "$RUN/logs/auto_deliver.log" 2>/dev/null | sed 's/^/  /'
echo
echo "=== 5. 生产核对 ==="
echo "  pool=$(ps -eo args | awk '/run_pool\.sh/ && !/awk/ && !/auto_deliver/ {c++} END {print c+0}') watchdog=$(ps -eo args | awk '/pool_watchdog\.sh --run \/home\/data\/agentmatrix_run / && !/awk/ {c++} END {print c+0}') auto=$(ps -eo args | awk '/auto_deliver\.sh --run/ && !/awk/ {c++} END {print c+0}')"
echo "  阈值: $(grep -o 'threshold=[0-9]*' "$RUN/logs/auto_deliver.log" | head -1)"
date -Is
