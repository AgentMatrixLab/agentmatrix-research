#!/usr/bin/env bash
# Fix the shard-tag bug, wipe suspect results, and restart cleanly.
#
# run_one_shard.sh used `printf "shard%03d" "$INDEX"`, which treats a leading-zero
# argument as octal. Indices containing 8 or 9 are invalid octal, printf fails, and
# the tag collapses onto another shard's directory (008 -> shard000, 010 -> shard008,
# 018 -> shard001 ...). About 100 of 213 shards were therefore writing into each
# other's directories, and run_pool.sh's "skip if oos manifest exists" check then
# skipped shards that had never actually run. The collected results are not
# trustworthy and the run has to start over with the fix.
set -u
RUN=/home/data/agentmatrix_run
cd "$RUN/agentmatrix" || exit 1

echo "=== 停掉所有 pool 与 worker ==="
for pid in $(ps -eo pid,args | awk '$2=="bash" && ($3 ~ /run_pool\.sh$/ || $3 ~ /run_one_shard\.sh$/) {print $1}'); do
  echo "  TERM $pid"; kill -TERM "$pid" 2>/dev/null
done
sleep 3
for pid in $(ps -eo pid,args | grep -E "[x]args|[r]un_one_shard|[b]uild_factor_values.py|[v]alidate-batch" | awk '{print $1}'); do
  kill -KILL "$pid" 2>/dev/null
done
sleep 3
echo "  残留: $(ps -eo args | grep -cE '[b]uild_factor|[v]alidate-batch|[r]un_one_shard')"

echo
echo "=== 确认修复在位 ==="
grep -n '10#' scripts/dev/run_one_shard.sh || { echo "  FATAL: 修复不在文件里"; exit 1; }

echo
echo "=== 清空被污染的分片结果 ==="
rm -rf "$RUN"/shards
rm -f "$RUN"/logs/shard*.log "$RUN"/logs/todo.txt
mkdir -p "$RUN/shards"
echo "  磁盘: $(df -h / | awk 'NR==2{print $4}')"

echo
echo "=== 重启（213 片，2 并行） ==="
setsid nohup bash scripts/dev/run_pool.sh 213 2 > "$RUN/logs/pool_driver.log" 2>&1 < /dev/null &
echo "  pool pid=$!"
sleep 45
echo "--- pool 日志（应无 octal 报错） ---"
head -12 "$RUN/logs/pool_driver.log"
echo "--- 正在跑的 worker ---"
ps -eo pid,etime,args | grep "[r]un_one_shard" | cut -c1-100
echo "--- 分片目录标签抽查 ---"
ls -d "$RUN"/shards/shard008 "$RUN"/shards/shard009 "$RUN"/shards/shard010 2>/dev/null
free -g | head -2
uptime
