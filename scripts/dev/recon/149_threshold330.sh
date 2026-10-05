RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
echo "=== 把 auto_deliver 的阈值从 308 调整为 330（按巡检指令的停止条件）==="
OLD=$(ps -eo pid,args | awk '/auto_deliver\.sh --run/ && !/awk/ {print $1; exit}')
if [ -n "$OLD" ]; then
  kill -TERM "$OLD" 2>/dev/null && echo "  已停旧实例 $OLD（阈值 308）"
  sleep 3
fi
rm -f "$RUN/logs/auto_deliver.log" "$RUN/logs/auto_deliver.done"
setsid nohup bash "$REPO/scripts/dev/auto_deliver.sh" --run "$RUN" --threshold 330 \
  --total 213 --interval 300 --deadline "2026-10-07 06:00" \
  > "$RUN/logs/auto_deliver.stdout" 2>&1 < /dev/null &
sleep 15
echo
echo "  --- 新实例 ---"
cat "$RUN/logs/auto_deliver.log" 2>/dev/null | sed 's/^/    /'
echo
echo "=== 阈值 330 对应的时间点 ==="
/home/data/conda-envs/rqsdk/bin/python -X utf8 - <<'PYEOF'
passed, done = 101, 44
rate = passed / done            # 通过数/片
need = 330 - passed
shards = need / rate
print("  每片通过 %.2f 个 → 还需 %.0f 片 ≈ %.1f 小时" % (rate, shards, shards / 6.4))
print("  ⇒ 预计触发约 10-06 %02d:%02d" % ((7 + int(shards / 6.4)) % 24, (24 + int((shards / 6.4) % 1 * 60)) % 60))
print("  ⇒ 进包预计 %d 个（阈值 330 减去 1 个风险暴露），高于 300 承诺" % (330 - 1))
PYEOF
echo
echo "=== 生产核对 ==="
echo "  run_pool.sh : $(ps -eo args | awk '/run_pool\.sh/ && !/awk/ && !/auto_deliver/ {c++} END {print c+0}')"
echo "  watchdog    : $(ps -eo args | awk '/pool_watchdog\.sh --run \/home\/data\/agentmatrix_run / && !/awk/ {c++} END {print c+0}')"
echo "  auto_deliver: $(ps -eo args | awk '/auto_deliver\.sh --run/ && !/awk/ {c++} END {print c+0}')（必须为 1）"
echo "  阈值确认    : $(ps -eo args | grep -o 'threshold=[0-9]*' <<< "$(cat $RUN/logs/auto_deliver.log 2>/dev/null)" | head -1)"
date -Is
