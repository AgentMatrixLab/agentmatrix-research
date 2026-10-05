RUN=/home/data/agentmatrix_run
cd "$RUN/agentmatrix" || exit 1

echo "=== 服务器上的 run_one_shard.sh 是否已修 ==="
if grep -q '10#' scripts/dev/run_one_shard.sh; then
  echo "  已是修复版"
else
  echo "  仍是 bug 版 -> 就地打补丁（只改这一行，不触碰其他文件）"
  cp scripts/dev/run_one_shard.sh scripts/dev/run_one_shard.sh.bak-octal
  sed -i 's|TAG=$(printf "shard%03d" "$INDEX")|TAG=$(printf "shard%03d" "$((10#$INDEX))")|' scripts/dev/run_one_shard.sh
  if grep -q '10#' scripts/dev/run_one_shard.sh; then
    echo "  补丁已应用"
  else
    echo "  FATAL: 补丁失败，手工处理"
    exit 1
  fi
fi
echo "  当前行: $(grep -n 'TAG=' scripts/dev/run_one_shard.sh | head -1)"

echo
echo "=== 服务器上是否也有并发同事的改动 ==="
ls -la research_core/factor_lab/streaming_supplement.py 2>/dev/null || echo "  (无 streaming_supplement.py)"

echo
echo "=== 当前 pool 与分片状态 ==="
echo "  pool 进程: $(ps -eo args | grep -c '[r]un_pool.sh')"
echo "  已完成的 oos 分片: $(ls $RUN/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l)"
echo "  分片目录数: $(ls -d $RUN/shards/shard*/ 2>/dev/null | wc -l)"
echo "  shard008 存在吗: $(test -d $RUN/shards/shard008 && echo 是 || echo 否)"
echo "  shard009 存在吗: $(test -d $RUN/shards/shard009 && echo 是 || echo 否)"

echo
echo "=== 最近的分片日志（看是否还有 octal 报错） ==="
grep -l "invalid octal" $RUN/logs/shard*.log 2>/dev/null | head -5
echo "  ^ 若列出文件，说明这些分片被 bug 影响过"

echo
echo "=== 资源 ==="
free -g | head -2
uptime
date -Is
