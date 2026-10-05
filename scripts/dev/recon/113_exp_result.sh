RUN=/home/data/agentmatrix_run
echo "=== 昂贵分片 shard023：jobs=1 vs jobs=4 ==="
grep -A6 'shard023：jobs=1 vs jobs=4' "$RUN/rehearsal/parallel_build2.log" 2>/dev/null | sed 's/^/  /'
echo
echo "=== 全量结果尾部 ==="
tail -10 "$RUN/rehearsal/parallel_build2.log" 2>/dev/null
echo
echo "=== 进程 ==="
ps -eo pid,etime,args | awk '/parallel2/ && !/awk/ {print "  " $1, $2}'
echo
echo "=== 用上并行构建的分片 ==="
for f in "$RUN"/logs/shard0*.log; do
  if grep -q 'building with' "$f" 2>/dev/null; then
    tag=$(basename "$f" .log)
    w=$(grep -o 'build wall=[0-9.]*s' "$f" | head -1)
    echo "  $tag  $w"
  fi
done
echo
echo "=== 进度 ==="
echo "  oos 完成: $(ls $RUN/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l) / 213"
date -Is
