RUN=/home/data/agentmatrix_run
SB=$RUN/rehearsal/watchdog_test
echo "=== 生产环境核对（最重要）==="
echo "  run_pool.sh (生产): $(ps -eo args | awk '/run_pool\.sh/ && !/awk/ && !/watchdog_test/ {c++} END {print c+0}')"
echo "  生产 watchdog     : $(ps -eo args | awk '/bash .*agentmatrix\/scripts\/dev\/pool_watchdog\.sh/ && !/awk/ {c++} END {print c+0}')"
echo "  在跑分片          : $(ps -eo args | awk '/run_one_shard\.sh [0-9]/ && !/awk/ {c++} END {print c+0}')"
echo "  oos 完成          : $(ls $RUN/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l) / 213"
echo "  parts             : $(ls $RUN/delivery/values/parts/*.parquet 2>/dev/null | wc -l)"
echo "  内存可用          : $(free -g | awk '/^Mem:/{print $7}')GB"
echo
echo "=== 沙箱残留进程（应清理）==="
ps -eo pid,etime,args | awk '/wd_test_pool|watchdog_test/ && !/awk/ {print "  " $1, $2, substr($0, index($0,$3), 80)}'
echo
echo "=== 沙箱测试结果（日志）==="
echo "  --- watchdog 决策日志 ---"
cat "$SB/logs/pool_watchdog.log" 2>/dev/null | sed 's/^/    /' || echo "    （无）"
echo "  --- 桩 pool 是否被拉起 ---"
cat "$SB/logs/stub_pool.log" 2>/dev/null | sed 's/^/    /' || echo "    （无——重启未被触发或被中断）"
echo "  --- watchdog 自身的 stdout ---"
cat "$SB/logs/pool_watchdog.stdout" 2>/dev/null | head -20 | sed 's/^/    /' || echo "    （无）"
echo
echo "=== 清理沙箱桩进程 ==="
for p in $(ps -eo pid,args | awk '/wd_test_pool\.sh|watchdog_test\/agentmatrix\/scripts/ && !/awk/ {print $1}'); do
  kill -KILL "$p" 2>/dev/null && echo "  已停 $p"
done
rm -rf "$SB/agentmatrix" 2>/dev/null && echo "  已移除沙箱桩 repo（防止再被拉起）"
echo
echo "=== 清理后生产核对 ==="
echo "  run_pool.sh: $(ps -eo args | awk '/run_pool\.sh/ && !/awk/ && !/watchdog_test/ {c++} END {print c+0}')"
echo "  watchdog   : $(ps -eo args | awk '/bash .*agentmatrix\/scripts\/dev\/pool_watchdog\.sh/ && !/awk/ {c++} END {print c+0}')"
echo "  oos 完成   : $(ls $RUN/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l) / 213"
date -Is
