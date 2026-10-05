RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
SB=$RUN/rehearsal/watchdog_test2
MARK=mark_wd2_guard
OUT=$RUN/rehearsal/watchdog_test2.log
cat > "$RUN/rehearsal/wd2.sh" <<'EOF'
#!/usr/bin/env bash
RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
SB=$RUN/rehearsal/watchdog_test2
MARK=mark_wd2_guard

echo "########## A. 换掉生产上那个旧 watchdog（TERM 不生效的那版）##########"
for p in $(ps -eo pid,args | awk -v m="$MARK" '$0 !~ m && /pool_watchdog\.sh --run \/home\/data\/agentmatrix_run / {print $1}'); do
  kill -KILL "$p" 2>/dev/null && echo "  KILL 旧 watchdog $p"
done
sleep 2

echo
echo "########## B. 搭建沙箱（桩 pool，独立于生产）##########"
rm -rf "$SB"; mkdir -p "$SB/shards/shard000/oos" "$SB/shards/shard001/oos" \
  "$SB/agentmatrix/scripts/dev" "$SB/logs"
echo '{}' > "$SB/shards/shard000/oos/batch_manifest.json"
echo '{}' > "$SB/shards/shard001/oos/batch_manifest.json"
cat > "$SB/agentmatrix/scripts/dev/run_pool.sh" <<'STUB'
#!/usr/bin/env bash
echo "STUB POOL LAUNCHED $(date -Is) stamp=${AGENTMATRIX_COMMIT:-unset} args=$*" \
  >> /home/data/agentmatrix_run/rehearsal/watchdog_test2/logs/stub_pool.log
sleep 300
STUB
chmod +x "$SB/agentmatrix/scripts/dev/run_pool.sh"
# run_one_shard.sh 也要存在，否则 watchdog 里的 sed 会报错
printf '#!/usr/bin/env bash\nsleep 300\n' > "$SB/agentmatrix/scripts/dev/run_one_shard.sh"
chmod +x "$SB/agentmatrix/scripts/dev/run_one_shard.sh"
echo "  沙箱: 2/5 片完成，桩 run_pool.sh 就绪"

echo
echo "########## C. 跑沙箱 watchdog（detached，输出到文件）##########"
setsid nohup bash "$REPO/scripts/dev/pool_watchdog.sh" \
  --run "$SB" --total 5 --interval 5 --cooldown 0 --stamp WDTEST \
  --pool-marker run_pool_stub_marker --shard-marker 'wd2_no_such_worker' \
  > "$SB/logs/wd.stdout" 2>&1 < /dev/null &
sleep 25

echo "  --- watchdog 决策日志 ---"
cat "$SB/logs/pool_watchdog.log" 2>/dev/null | sed 's/^/    /'
echo "  --- 桩 pool 是否被拉起（重启路径的关键证据）---"
cat "$SB/logs/stub_pool.log" 2>/dev/null | sed 's/^/    /' || echo "    ** 未拉起 **"

echo
echo "########## D. 验证 TERM 现在真的能停（旧的会忽略）##########"
WDPID=$(cat "$SB/logs/pool_watchdog.lock/pid" 2>/dev/null)
echo "  沙箱 watchdog pid=$WDPID"
if [ -n "$WDPID" ]; then
  kill -TERM "$WDPID" 2>/dev/null
  sleep 5
  if kill -0 "$WDPID" 2>/dev/null; then
    echo "  ** 仍然存活——TERM 修复无效 **"
    kill -KILL "$WDPID" 2>/dev/null
  else
    echo "  TERM 后已退出：修复有效"
  fi
fi
echo "  --- 退出日志 ---"
tail -2 "$SB/logs/pool_watchdog.log" 2>/dev/null | sed 's/^/    /'

echo
echo "########## E. 清理沙箱 + 启动修好的生产 watchdog ##########"
for p in $(ps -eo pid,args | awk -v m="$MARK" '$0 !~ m && /watchdog_test2/ {print $1}'); do
  kill -KILL "$p" 2>/dev/null && echo "  清理沙箱进程 $p"
done
rm -rf "$SB/agentmatrix" "$SB/logs/pool_watchdog.lock" 2>/dev/null

rm -rf "$RUN/logs/pool_watchdog.lock" 2>/dev/null
setsid nohup bash "$REPO/scripts/dev/pool_watchdog.sh" --run "$RUN" --total 213 \
  > "$RUN/logs/pool_watchdog.stdout" 2>&1 < /dev/null &
sleep 15
echo "  新 watchdog 日志:"
tail -3 "$RUN/logs/pool_watchdog.log" 2>/dev/null | sed 's/^/    /'
echo "  锁内 pid: $(cat $RUN/logs/pool_watchdog.lock/pid 2>/dev/null)"

echo
echo "########## F. 生产核对 ##########"
echo "  run_pool.sh        : $(ps -eo args | awk '/run_pool\.sh/ && !/awk/ && !/watchdog_test/ {c++} END {print c+0}')"
echo "  生产 watchdog      : $(ps -eo args | awk '/pool_watchdog\.sh --run \/home\/data\/agentmatrix_run / && !/awk/ {c++} END {print c+0}')"
echo "  在跑分片           : $(ps -eo args | awk '/run_one_shard\.sh [0-9]/ && !/awk/ {c++} END {print c+0}')"
echo "  oos 完成           : $(ls $RUN/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l) / 213"
echo "########## 结束 $(date -Is) ##########"
EOF
sed -i 's/\r$//' "$RUN/rehearsal/wd2.sh"
chmod +x "$RUN/rehearsal/wd2.sh"
setsid nohup bash "$RUN/rehearsal/wd2.sh" > "$OUT" 2>&1 < /dev/null &
echo "  已启动（detached）"
date -Is
