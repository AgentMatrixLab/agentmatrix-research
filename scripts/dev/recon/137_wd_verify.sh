RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
SB=$RUN/rehearsal/wd_verify
echo "=== 1. 杀掉遗留的旧 watchdog（TERM 无效那版）==="
for p in $(ps -eo pid,args | awk '/pool_watchdog\.sh --run \/home\/data\/agentmatrix_run / && !/awk/ {print $1}'); do
  kill -KILL "$p" 2>/dev/null && echo "  KILL $p"
done
rm -rf "$RUN/logs/pool_watchdog.lock" 2>/dev/null
sleep 2

echo
echo "=== 2. 检测函数语义测试（关键：marker 不出现在 awk 自己的参数里）==="
# 模拟真实 ps 输出中含 awk 自己的情形
ps -eo pid,args > "$SB.ps" 2>/dev/null || mkdir -p "$SB" && ps -eo pid,args > "$SB.ps"
echo "  当前 ps 行数: $(wc -l < "$SB.ps")"
WD_PATTERN='zzz_never_matches_zzz' awk -v me="99999999" -v mode="literal" '
  BEGIN { pat = ENVIRON["WD_PATTERN"] }
  $1 == me { next }
  $0 ~ /pool_watchdog/ { next }
  $0 ~ /[a]wk -v me=/ { next }
  mode == "literal" ? (index($0, pat) > 0) : ($0 ~ pat) { c++ }
  END { print "  不存在匹配时应为 0 ->", c+0 }' < "$SB.ps"
WD_PATTERN='run_pool.sh' awk -v me="99999999" -v mode="literal" '
  BEGIN { pat = ENVIRON["WD_PATTERN"] }
  $1 == me { next }
  $0 ~ /pool_watchdog/ { next }
  $0 ~ /[a]wk -v me=/ { next }
  mode == "literal" ? (index($0, pat) > 0) : ($0 ~ pat) { c++ }
  END { print "  真实生产 pool 应 >=1 ->", c+0 }' < "$SB.ps"
echo "  （若第一项为 0 且第二项 >=1，检测逻辑正确）"

echo
echo "=== 3. 沙箱端到端：确认重启真的会发生 ==="
rm -rf "$SB"; mkdir -p "$SB/shards/shard000/oos" "$SB/shards/shard001/oos" \
  "$SB/agentmatrix/scripts/dev" "$SB/logs"
echo '{}' > "$SB/shards/shard000/oos/batch_manifest.json"
echo '{}' > "$SB/shards/shard001/oos/batch_manifest.json"
cat > "$SB/agentmatrix/scripts/dev/run_pool.sh" <<'STUB'
#!/usr/bin/env bash
echo "STUB POOL LAUNCHED $(date -Is) stamp=${AGENTMATRIX_COMMIT:-unset} args=$*" \
  >> /home/data/agentmatrix_run/rehearsal/wd_verify/logs/stub_pool.log
sleep 240
STUB
chmod +x "$SB/agentmatrix/scripts/dev/run_pool.sh"
printf '#!/usr/bin/env bash\nsleep 240\n' > "$SB/agentmatrix/scripts/dev/run_one_shard.sh"
chmod +x "$SB/agentmatrix/scripts/dev/run_one_shard.sh"
setsid nohup bash "$REPO/scripts/dev/pool_watchdog.sh" \
  --run "$SB" --total 5 --interval 5 --cooldown 60 --stamp WDTEST \
  --pool-marker wd_verify --shard-marker 'wd_verify_no_worker' \
  > "$SB/logs/wd.stdout" 2>&1 < /dev/null &
sleep 50
echo "  --- watchdog 日志 ---"
cat "$SB/logs/pool_watchdog.log" 2>/dev/null | sed 's/^/    /'
echo "  --- 桩 pool 是否被拉起 ---"
cat "$SB/logs/stub_pool.log" 2>/dev/null | sed 's/^/    /' || echo "    ** 未拉起 **"
echo "  --- stdout 错误 ---"
head -6 "$SB/logs/wd.stdout" 2>/dev/null | sed 's/^/    /'

echo
echo "=== 4. 清理沙箱 + 启动唯一的生产 watchdog ==="
for p in $(ps -eo pid,args | awk '/wd_verify/ && !/awk/ {print $1}'); do kill -KILL "$p" 2>/dev/null; done
rm -rf "$SB/agentmatrix" "$SB/logs/pool_watchdog.lock" 2>/dev/null
setsid nohup bash "$REPO/scripts/dev/pool_watchdog.sh" --run "$RUN" --total 213 \
  > "$RUN/logs/pool_watchdog.stdout" 2>&1 < /dev/null &
sleep 15

echo
echo "=== 5. 生产核对 ==="
echo "  生产 watchdog 进程数: $(ps -eo args | awk '/pool_watchdog\.sh --run \/home\/data\/agentmatrix_run / && !/awk/ {c++} END {print c+0}')（必须为 1）"
echo "  锁内 pid            : $(cat $RUN/logs/pool_watchdog.lock/pid 2>/dev/null)"
echo "  run_pool.sh         : $(ps -eo args | awk '/run_pool\.sh/ && !/awk/ && !/wd_verify/ {c++} END {print c+0}')"
echo "  在跑分片            : $(ps -eo args | awk '/run_one_shard\.sh [0-9]/ && !/awk/ {c++} END {print c+0}')"
echo "  oos 完成            : $(ls $RUN/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l) / 213"
date -Is
