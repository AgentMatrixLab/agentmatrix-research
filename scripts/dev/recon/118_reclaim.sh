RUN=/home/data/agentmatrix_run
echo "=== 清理前 ==="
df -h / | awk 'NR==2{print "  可用 "$4}'

echo
echo "=== 将删除的彩排大文件（显式列举，不匹配即不删）==="
TOTAL=0
for f in \
  "$RUN/scratch/rebuild_probe/factor_values.parquet" \
  "$RUN/rehearsal/consolidated_check.parquet" \
  "$RUN/rehearsal/parallel/c022_j1.parquet" \
  "$RUN/rehearsal/parallel/c022_j4.parquet" \
  "$RUN/rehearsal/parallel2/c022_j1.parquet" \
  "$RUN/rehearsal/parallel2/c022_j4.parquet" \
  "$RUN/rehearsal/parallel2/c023_j1.parquet" \
  "$RUN/rehearsal/parallel2/c023_j4.parquet" \
  "$RUN/rehearsal/scale30/factor_values.parquet" \
  ; do
  if [ -f "$f" ]; then
    sz=$(stat -c %s "$f")
    printf "  %8.1f MB  %s\n" "$(echo "$sz/1000000" | bc -l)" "$f"
    TOTAL=$((TOTAL + sz))
  fi
done
printf "  合计 %.2f GB\n" "$(echo "$TOTAL/1000000000" | bc -l)"

echo
echo "=== 保留的证据（不删）==="
for f in "$RUN/scratch/rebuild_probe/probe.log" "$RUN/rehearsal/parallel_build2.log" \
         "$RUN/rehearsal/consolidate_speed.log" "$RUN/rehearsal/stream_speed.log" \
         "$RUN/rehearsal/scale30.log" "$RUN/rehearsal/panel_cols.log" \
         "$RUN/rehearsal/jobs_check.log" "$RUN/rehearsal/memcheck.log" \
         "$RUN/rehearsal/rss_profile.log" "$RUN/rehearsal/scope_check.log" \
         "$RUN/rehearsal/package_check.log" "$RUN/rehearsal/reconcile_check.log"; do
  [ -f "$f" ] && echo "  $(du -h "$f" | cut -f1)  $(basename "$f")"
done

echo
echo "=== 执行删除 ==="
for f in \
  "$RUN/scratch/rebuild_probe/factor_values.parquet" \
  "$RUN/rehearsal/consolidated_check.parquet" \
  "$RUN/rehearsal/parallel/c022_j1.parquet" \
  "$RUN/rehearsal/parallel/c022_j4.parquet" \
  "$RUN/rehearsal/parallel2/c022_j1.parquet" \
  "$RUN/rehearsal/parallel2/c022_j4.parquet" \
  "$RUN/rehearsal/parallel2/c023_j1.parquet" \
  "$RUN/rehearsal/parallel2/c023_j4.parquet" \
  "$RUN/rehearsal/scale30/factor_values.parquet" \
  ; do
  [ -f "$f" ] && rm -f "$f" && echo "  removed $(basename "$f")"
done
# sidecars of the deleted datasets
rm -f "$RUN/rehearsal/consolidated_check.parquet.json" "$RUN/rehearsal/scale30/factor_values.parquet.json" \
      "$RUN/scratch/rebuild_probe/factor_values.parquet.json" 2>/dev/null

echo
echo "=== 清理后 ==="
df -h / | awk 'NR==2{print "  可用 "$4}'
echo
echo "  交付目录（必须保留，勿动）:"
for d in "$RUN/delivery/values/parts" "$RUN/delivery/values/raw" "$RUN/reference" "$RUN/runtime_mirror"; do
  [ -e "$d" ] && echo "    $(du -sh "$d" 2>/dev/null | cut -f1)  $d"
done
echo
echo "=== pool 未受影响 ==="
echo "  oos 完成: $(ls $RUN/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l) / 213"
ps -eo pid,etime,args | awk '/run_one_shard\.sh [0-9]|retain_passing|mirror_runtime/ && !/awk/ {print "  " $1, $2}'
date -Is
