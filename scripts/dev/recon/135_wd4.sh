RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
OUT=$RUN/rehearsal/wd4.log
cat > "$RUN/rehearsal/wd4.sh" <<'EOF'
#!/usr/bin/env bash
RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
SB=$RUN/rehearsal/watchdog_test3
echo "########## A. 沙箱：5 片里完成 2 片，桩 pool 未运行 ##########"
rm -rf "$SB"; mkdir -p "$SB/shards/shard000/oos" "$SB/shards/shard001/oos" \
  "$SB/agentmatrix/scripts/dev" "$SB/logs"
echo '{}' > "$SB/shards/shard000/oos/batch_manifest.json"
echo '{}' > "$SB/shards/shard001/oos/batch_manifest.json"
cat > "$SB/agentmatrix/scripts/dev/run_pool.sh" <<'STUB'
#!/usr/bin/env bash
echo "STUB POOL LAUNCHED $(date -Is) stamp=${AGENTMATRIX_COMMIT:-unset} args=$*" \
  >> /home/data/agentmatrix_run/rehearsal/watchdog_test3/logs/stub_pool.log
sleep 240
STUB
chmod +x "$SB/agentmatrix/scripts/dev/run_pool.sh"
printf '#!/usr/bin/env bash\nsleep 240\n' > "$SB/agentmatrix/scripts/dev/run_one_shard.sh"
chmod +x "$SB/agentmatrix/scripts/dev/run_one_shard.sh"
echo "  就绪"
echo
echo "########## B. marker 用沙箱路径（桩被拉起后其命令行会含此串，符合真实语义）##########"
setsid nohup bash "$REPO/scripts/dev/pool_watchdog.sh" \
  --run "$SB" --total 5 --interval 5 --cooldown 60 --stamp WDTEST \
  --pool-marker watchdog_test3 --shard-marker 'wd4_no_such_worker' \
  > "$SB/logs/wd.stdout" 2>&1 < /dev/null &
echo "  已启动，观察 70 秒"
sleep 70
echo
echo "  --- watchdog 决策日志（应含 restart 一行）---"
cat "$SB/logs/pool_watchdog.log" 2>/dev/null | sed 's/^/    /'
echo "  --- 桩 pool 日志（重启路径的证据）---"
cat "$SB/logs/stub_pool.log" 2>/dev/null | sed 's/^/    /' || echo "    ** 未拉起 **"
echo "  --- watchdog stdout（若重启失败，原因在此）---"
head -12 "$SB/logs/wd.stdout" 2>/dev/null | sed 's/^/    /'
echo
echo "  --- 是否只重启了一次（桩活着时不应再重启）---"
echo "    restart 行数: $(grep -c 'restart #' "$SB/logs/pool_watchdog.log" 2>/dev/null)"
echo "    桩被拉起次数: $(wc -l < "$SB/logs/stub_pool.log" 2>/dev/null || echo 0)"
echo
echo "########## C. TERM 停止 + 清理沙箱 ##########"
WDPID=$(cat "$SB/logs/pool_watchdog.lock/pid" 2>/dev/null)
[ -n "$WDPID" ] && kill -TERM "$WDPID" 2>/dev/null && sleep 4
echo "  沙箱 watchdog 是否已退出: $(kill -0 "$WDPID" 2>/dev/null && echo 否 || echo 是)"
for p in $(ps -eo pid,args | awk '/watchdog_test3/ && !/awk/ {print $1}'); do
  kill -KILL "$p" 2>/dev/null
done
rm -rf "$SB/agentmatrix" "$SB/logs/pool_watchdog.lock" 2>/dev/null
echo "  沙箱残留: $(ps -eo args | awk '/watchdog_test3/ && !/awk/ {c++} END {print c+0}')"
echo
echo "########## D. 把生产 watchdog 换成修订版 ##########"
for p in $(ps -eo pid,args | awk '/pool_watchdog\.sh --run \/home\/data\/agentmatrix_run / && !/awk/ {print $1}'); do
  kill -TERM "$p" 2>/dev/null && echo "  TERM 旧 watchdog $p"
done
sleep 5
rm -rf "$RUN/logs/pool_watchdog.lock" 2>/dev/null
setsid nohup bash "$REPO/scripts/dev/pool_watchdog.sh" --run "$RUN" --total 213 \
  > "$RUN/logs/pool_watchdog.stdout" 2>&1 < /dev/null &
sleep 15
echo "  新 watchdog pid: $(cat $RUN/logs/pool_watchdog.lock/pid 2>/dev/null)"
echo
echo "########## E. 生产核对 ##########"
echo "  run_pool.sh   : $(ps -eo args | awk '/run_pool\.sh/ && !/awk/ && !/watchdog_test/ {c++} END {print c+0}')"
echo "  生产 watchdog : $(ps -eo args | awk '/pool_watchdog\.sh --run \/home\/data\/agentmatrix_run / && !/awk/ {c++} END {print c+0}')"
echo "  在跑分片      : $(ps -eo args | awk '/run_one_shard\.sh [0-9]/ && !/awk/ {c++} END {print c+0}')"
echo "  oos 完成      : $(ls $RUN/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l) / 213"
echo "########## 结束 $(date -Is) ##########"
EOF
sed -i 's/\r$//' "$RUN/rehearsal/wd4.sh"; chmod +x "$RUN/rehearsal/wd4.sh"
setsid nohup bash "$RUN/rehearsal/wd4.sh" > "$OUT" 2>&1 < /dev/null &
echo "  已启动（detached，约 2 分钟）"
date -Is
