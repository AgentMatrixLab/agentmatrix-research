RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
SB=$RUN/rehearsal/wd_trace
echo "=== 搭建最小沙箱 ==="
rm -rf "$SB"; mkdir -p "$SB/shards/shard000/oos" "$SB/shards/shard001/oos" "$SB/logs"
echo '{}' > "$SB/shards/shard000/oos/batch_manifest.json"
echo '{}' > "$SB/shards/shard001/oos/batch_manifest.json"
echo "  2/5 完成"
echo
echo "=== 前台 bash -x 追踪（15 秒足够看清决策路径）==="
timeout 15 bash -x "$REPO/scripts/dev/pool_watchdog.sh" \
  --run "$SB" --total 5 --interval 5 --cooldown 60 --stamp WDTEST \
  --pool-marker wd_trace_should_not_match_anything \
  --shard-marker 'wd_trace_no_worker' > "$SB/trace.log" 2>&1
echo "  退出码 $?（124 = timeout 终止，说明它在循环里）"
echo
echo "=== 追踪中的关键决策 ==="
grep -nE '^\+{1,2} (done_n|pool_running|shard_running|chain_running|completed|inflight|now|since|restarts|last_restart|cd|setsid|log)' "$SB/trace.log" 2>/dev/null | head -40 | sed 's/^/  /'
echo
echo "=== 追踪里 restart 相关行 ==="
grep -n 'restart\|pool is down\|cooldown\|all .* complete\|refusing' "$SB/trace.log" 2>/dev/null | head -15 | sed 's/^/  /'
echo
echo "=== 追踪尾部（看它卡在哪）==="
tail -18 "$SB/trace.log" 2>/dev/null | sed 's/^/  /'
echo
echo "=== 生产 watchdog 数量核对（刚才显示 2）==="
ps -eo pid,etime,args | awk '/pool_watchdog\.sh/ && !/awk/ {print "  " $1, $2, substr($0, index($0,$3), 95)}'
echo "  锁内 pid: $(cat $RUN/logs/pool_watchdog.lock/pid 2>/dev/null)"
echo
echo "=== 生产状态 ==="
echo "  run_pool.sh: $(ps -eo args | awk '/run_pool\.sh/ && !/awk/ && !/wd_trace/ {c++} END {print c+0}')"
echo "  oos 完成   : $(ls $RUN/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l) / 213"
date -Is
