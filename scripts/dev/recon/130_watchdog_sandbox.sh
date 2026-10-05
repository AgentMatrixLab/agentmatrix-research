RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
SB=$RUN/rehearsal/watchdog_test
echo "=== 搭建沙箱（完全独立于生产环境）==="
rm -rf "$SB"; mkdir -p "$SB/shards/shard000/oos" "$SB/shards/shard001/oos" "$SB/agentmatrix/scripts/dev" "$SB/logs"
# 5 片里完成 2 片 -> 未完成，应当触发重启
echo '{}' > "$SB/shards/shard000/oos/batch_manifest.json"
echo '{}' > "$SB/shards/shard001/oos/batch_manifest.json"
# 桩 pool：被拉起时写标记然后长睡，模拟一个真的 pool
cat > "$SB/agentmatrix/scripts/dev/wd_test_pool.sh" <<'EOF'
#!/usr/bin/env bash
echo "STUB POOL LAUNCHED $(date -Is) stamp=${AGENTMATRIX_COMMIT:-unset} args=$*" >> "$RUN/rehearsal/watchdog_test/logs/stub_pool.log"
sleep 600
EOF
sed -i 's/\r$//' "$SB/agentmatrix/scripts/dev/wd_test_pool.sh"
chmod +x "$SB/agentmatrix/scripts/dev/wd_test_pool.sh"
# 桩 shard worker：不启动，用于验证「有 worker 就不抢」
echo "  沙箱就绪: $(ls $SB/shards/shard*/oos/batch_manifest.json | wc -l) 片完成 / 5"

echo
echo "=== 关键技巧：watchdog 硬编码了 run_pool.sh，沙箱需让它拉起桩 ==="
echo "  做法：在沙箱 repo 里放一个 run_pool.sh 桩，并用 --pool-marker 指向它"
cp "$SB/agentmatrix/scripts/dev/wd_test_pool.sh" "$SB/agentmatrix/scripts/dev/run_pool.sh"
sed -i 's/wd_test_pool/run_pool_stub_marker/' "$SB/agentmatrix/scripts/dev/run_pool.sh"
chmod +x "$SB/agentmatrix/scripts/dev/run_pool.sh"
grep -c 'run_pool_stub_marker' "$SB/agentmatrix/scripts/dev/run_pool.sh" | sed 's/^/  桩内标记数: /'

echo
echo "=== 运行 watchdog（沙箱参数，interval 5s，cooldown 0）==="
timeout 60 bash "$REPO/scripts/dev/pool_watchdog.sh" \
  --run "$SB" --total 5 --interval 5 --cooldown 0 --stamp WDTEST \
  --pool-marker run_pool_stub_marker \
  --shard-marker 'wd_test_no_such_worker' 2>&1 | sed 's/^/  /'
echo "  （timeout 60 结束，属预期）"

echo
echo "=== watchdog 日志 ==="
cat "$SB/logs/pool_watchdog.log" 2>/dev/null | sed 's/^/  /'
echo
echo "=== 桩 pool 是否真的被拉起 ==="
cat "$SB/logs/stub_pool.log" 2>/dev/null | sed 's/^/  /' || echo "  ** 桩未被拉起——重启路径有问题 **"
echo
echo "=== 清理沙箱桩进程 ==="
for p in $(ps -eo pid,args | awk '/wd_test_pool|watchdog_test\/agentmatrix/ && !/awk/ {print $1}'); do
  kill -TERM "$p" 2>/dev/null && echo "  已停 $p"
done
echo
echo "=== 生产 pool 与 watchdog 未受影响 ==="
echo "  run_pool.sh: $(ps -eo args | awk '/run_pool\.sh/ && !/awk/ && !/watchdog_test/ {c++} END {print c+0}')"
echo "  watchdog   : $(ps -eo args | awk '/bash .*agentmatrix\/scripts\/dev\/pool_watchdog\.sh/ && !/awk/ {c++} END {print c+0}')"
echo "  oos 完成   : $(ls $RUN/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l) / 213"
date -Is
