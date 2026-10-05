RUN=/home/data/agentmatrix_run
SB=$RUN/rehearsal/watchdog_test
MARK=mark_wd_stop_guard
echo "=== 1. 停掉沙箱 watchdog（TERM 被旧版忽略，用 KILL）==="
for p in $(ps -eo pid,args | awk -v m="$MARK" '$0 !~ m && /watchdog_test/ && /pool_watchdog/ {print $1}'); do
  kill -KILL "$p" 2>/dev/null && echo "  KILL $p"
done
for p in $(ps -eo pid,args | awk -v m="$MARK" '$0 !~ m && /timeout 60 bash/ && /pool_watchdog/ {print $1}'); do
  kill -KILL "$p" 2>/dev/null && echo "  KILL timeout wrapper $p"
done
rm -rf "$SB/logs/pool_watchdog.lock" 2>/dev/null
sleep 2
echo "  沙箱 watchdog 残留: $(ps -eo args | awk '/watchdog_test/ && /pool_watchdog/ && !/awk/ {c++} END {print c+0}')"

echo
echo "=== 2. 精确区分生产与沙箱（此前那个 3 是把沙箱也算进去了）==="
echo "  生产 run_pool.sh    : $(ps -eo args | awk '/run_pool\.sh/ && !/awk/ && !/watchdog_test/ {c++} END {print c+0}')"
echo "  生产 watchdog（按运行目录）: $(ps -eo args | awk '/pool_watchdog\.sh --run \/home\/data\/agentmatrix_run / && !/awk/ {c++} END {print c+0}')"
echo "  所有 pool_watchdog 进程:"
ps -eo pid,etime,args | awk '/pool_watchdog\.sh/ && !/awk/ {print "    " $1, $2, substr($0, index($0,$3), 90)}'

echo
echo "=== 3. 部署修好的 watchdog（TERM 现在会退出）==="
# put 由本地完成，这里只做语法与行为核对
bash -n /home/data/agentmatrix_run/agentmatrix/scripts/dev/pool_watchdog.sh && echo "  bash -n OK"
grep -n 'on_signal\|trap ' /home/data/agentmatrix_run/agentmatrix/scripts/dev/pool_watchdog.sh | sed 's/^/    /'

echo
echo "=== 4. 生产状态核对 ==="
echo "  oos 完成: $(ls $RUN/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l) / 213"
echo "  parts   : $(ls $RUN/delivery/values/parts/*.parquet 2>/dev/null | wc -l)"
echo "  在跑分片: $(ps -eo args | awk '/run_one_shard\.sh [0-9]/ && !/awk/ {c++} END {print c+0}')"
echo "  内存可用: $(free -g | awk '/^Mem:/{print $7}')GB"
date -Is
