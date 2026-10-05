RUN=/home/data/agentmatrix_run
echo "=== 已完成分片的阶段耗时 ==="
for f in $(ls -t "$RUN"/logs/shard*.log 2>/dev/null | head -12); do
  name=$(basename "$f")
  b=$(grep -o "build wall=[0-9.]*s" "$f" 2>/dev/null | tail -1)
  t=$(grep -o "train wall=[0-9.]*s" "$f" 2>/dev/null | tail -1)
  o=$(grep -o "oos wall=[0-9.]*s" "$f" 2>/dev/null | tail -1)
  done_=$(grep -c "done" "$f" 2>/dev/null)
  printf "  %-14s %-18s %-18s %-18s done=%s\n" "$name" "${b:- -}" "${t:- -}" "${o:- -}" "$done_"
done

echo
echo "=== 失败的分片及其完整错误 ==="
for f in $(grep -l "FAILED" "$RUN"/logs/shard*.log 2>/dev/null | head -2); do
  echo "---- $(basename "$f") ----"
  grep -B12 "FAILED" "$f" | tail -18
done

echo
echo "=== 累计 ==="
echo "  train: $(ls $RUN/shards/shard*/train/batch_manifest.json 2>/dev/null | wc -l)"
echo "  oos  : $(ls $RUN/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l)"
echo "  驱动已启动: $(grep -c 'started' $RUN/logs/sharded_driver.log)"
echo "  驱动运行时长: $(ps -eo etime,args | grep '[r]un_sharded.sh 213' | head -1 | awk '{print $1}')"
date -Is
