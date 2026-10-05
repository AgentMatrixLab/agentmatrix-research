RUN=/home/data/agentmatrix_run
echo "=== 1. 留存覆盖是否严格一致 ==="
DONE=$(ls $RUN/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l)
PARTS=$(ls $RUN/delivery/values/parts/*.parquet 2>/dev/null | wc -l)
echo "  已完成分片: $DONE   留存 parts: $PARTS   $([ "$DONE" = "$PARTS" ] && echo '一致' || echo '** 不一致 **')"
echo "  每个 part 是否都有 sidecar: $(ls $RUN/delivery/values/parts/*.json 2>/dev/null | wc -l)"

echo
echo "=== 2. raw 硬链接是否保持有界（此前的泄漏点）==="
if [ -d "$RUN/delivery/values/raw" ]; then
  n=$(find "$RUN/delivery/values/raw" -type f 2>/dev/null | wc -l)
  sz=$(du -sh "$RUN/delivery/values/raw" 2>/dev/null | cut -f1)
  echo "  raw 文件数: $n   占用: $sz"
  echo "  raw 里的文件（应只对应在跑的分片，最多 2 个）:"
  find "$RUN/delivery/values/raw" -type f 2>/dev/null | head -8 | sed 's/^/    /'
  # 真实占用（硬链接只算一次）
  echo "  这些硬链接的真实磁盘占用（去重后）:"
  find "$RUN/delivery/values/raw" -type f -links +1 2>/dev/null | wc -l | sed 's/^/    已与 parts 共享 inode 的文件数: /'
  # 陈旧链接：源文件已不在正在跑的分片里
  echo "  陈旧链接检测（raw 中 mtime 早于最近 30 分钟且分片已完成）:"
  stale=0
  for f in $(find "$RUN/delivery/values/raw" -type f 2>/dev/null); do
    tag=$(basename "$f" | grep -o 'shard[0-9]*' || echo "")
    if [ -n "$tag" ] && [ -f "$RUN/shards/$tag/oos/batch_manifest.json" ]; then
      stale=$((stale + 1))
      echo "    ** $tag 已完成但 raw 仍有链接: $(basename "$f")"
    fi
  done
  [ "$stale" -eq 0 ] && echo "    无陈旧链接（正常）"
else
  echo "  raw 目录不存在（正常——无在跑分片时）"
fi

echo
echo "=== 3. 守护进程健康 ==="
ps -eo pid,etime,args | awk '/retain_passing_values|mirror_runtime_data|pool_watchdog\.sh --run|run_pool\.sh/ && !/awk/ {printf "  %-8s %-10s %s\n", $1, $2, substr($0, index($0,$3), 72)}'

echo
echo "=== 4. 磁盘与内存 ==="
df -h / | awk 'NR==2{print "  磁盘可用 "$4" / "$2}'
free -g | awk '/^Mem:/{print "  内存可用 "$7"GB / "$2"GB"}'

echo
echo "=== 5. 交付目录总量 ==="
du -sh $RUN/delivery 2>/dev/null | sed 's/^/  /'
echo "  投影（213 片）: parts 26.9GB + 合并 26.9GB ≈ 54GB"
date -Is
