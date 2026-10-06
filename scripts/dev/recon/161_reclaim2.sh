RUN=/home/data/agentmatrix_run
echo "=== 清理前 ==="
df -h / | awk 'NR==2{print "  可用 "$4}'
echo
echo "=== 我的彩排留下的大文件（显式列举才删）==="
TOTAL=0
for f in \
  "$RUN/rehearsal/scale60/factor_values.parquet" \
  "$RUN/rehearsal/scale50/factor_values.parquet" \
  "$RUN/delivery/rebuild/factor_values.parquet" \
  "$RUN/rehearsal/scale30/factor_values.parquet" \
  ; do
  if [ -f "$f" ]; then
    sz=$(stat -c %s "$f")
    printf "  %8.2f GB  %s\n" "$(echo "$sz/1000000000" | bc -l)" "$f"
    TOTAL=$((TOTAL + sz))
  fi
done
printf "  合计 %.2f GB\n" "$(echo "$TOTAL/1000000000" | bc -l)"
echo
echo "=== 保留的证据日志（不删）==="
ls -la "$RUN/rehearsal"/*.log 2>/dev/null | awk '{print "  " $5, $9}' | head -14
echo
echo "=== 执行删除（只删上面列举的数据文件）==="
for f in \
  "$RUN/rehearsal/scale60/factor_values.parquet" \
  "$RUN/rehearsal/scale50/factor_values.parquet" \
  "$RUN/delivery/rebuild/factor_values.parquet" \
  "$RUN/rehearsal/scale30/factor_values.parquet" \
  ; do
  [ -f "$f" ] && rm -f "$f" && echo "  removed $(basename $(dirname "$f"))/$(basename "$f")"
done
rm -f "$RUN/rehearsal/scale60/factor_values.parquet.json" \
      "$RUN/rehearsal/scale50/factor_values.parquet.json" \
      "$RUN/delivery/rebuild/factor_values.parquet.json" \
      "$RUN/rehearsal/scale30/factor_values.parquet.json" 2>/dev/null
# scale30/scale60 里还有合并出来的 sidecar 与包，规模不大，留作证据
echo
echo "=== 清理后 ==="
df -h / | awk 'NR==2{print "  可用 "$4}'
echo
echo "=== 交付相关目录（必须保留）==="
for d in "$RUN/delivery/values/parts" "$RUN/delivery/values/raw" "$RUN/reference" "$RUN/runtime_mirror"; do
  [ -e "$d" ] && echo "  $(du -sh "$d" 2>/dev/null | cut -f1)  $d"
done
echo
echo "=== 交付期磁盘投影 ==="
/home/data/conda-envs/rqsdk/bin/python -X utf8 - <<'PYEOF'
import glob, os, shutil
parts = glob.glob("/home/data/agentmatrix_run/delivery/values/parts/*.parquet")
avg = sum(os.path.getsize(p) for p in parts) / len(parts)
free = shutil.disk_usage("/").free
for n in (141, 213):
    need = 2 * avg * n          # parts + consolidated
    print("  %d 片: parts+合并 ≈ %.1f GB，剩余 %.1f GB → %s" % (
        n, need / 1e9, (free - need) / 1e9,
        "充足" if free - need > 20e9 else "偏紧"))
PYEOF
echo
echo "=== pool 未受影响 ==="
echo "  oos 完成: $(ls $RUN/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l) / 213"
echo "  在跑: $(ps -eo args | awk '/run_one_shard\.sh [0-9]/ && !/awk/ {c++} END {print c+0}')  守护: $(ps -eo args | awk '/run_pool\.sh|pool_watchdog\.sh --run|auto_deliver\.sh --run/ && !/awk/ {c++} END {print c+0}')"
date -Is
