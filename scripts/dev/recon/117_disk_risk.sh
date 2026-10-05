RUN=/home/data/agentmatrix_run
echo "=== 磁盘现状 ==="
df -h / | awk 'NR==2{print "  可用 "$4" / 总 "$2"  已用 "$5}'
echo
echo "=== 各目录占用 ==="
du -sh "$RUN"/* 2>/dev/null | sort -hr | head -14 | sed 's/^/  /'
echo
echo "=== 交付相关目录明细 ==="
for d in "$RUN/delivery/values/parts" "$RUN/delivery/values/raw" "$RUN/rehearsal" "$RUN/runtime_mirror" "$RUN/shards" "$RUN/reference"; do
  [ -e "$d" ] && echo "  $(du -sh "$d" 2>/dev/null | cut -f1)  $d"
done
echo
echo "=== 全量投影（213 分片）==="
/home/data/conda-envs/rqsdk/bin/python -X utf8 - <<'PYEOF'
import glob, os, shutil
parts = glob.glob("/home/data/agentmatrix_run/delivery/values/parts/*.parquet")
sizes = [os.path.getsize(p) for p in parts]
if not sizes:
    print("  尚无 parts"); raise SystemExit(0)
avg = sum(sizes) / len(sizes)
total = shutil.disk_usage("/")
print("  已完成分片 %d 个，parts 平均 %.0f MB（最大 %.0f MB）" % (
    len(parts), avg / 1e6, max(sizes) / 1e6))
proj_parts = avg * 213
print("  213 分片的 parts 投影     : %.1f GB" % (proj_parts / 1e9))
print("  合并后单文件（同量级）    : %.1f GB" % (proj_parts / 1e9))
print("  合计新增                  : %.1f GB" % (2 * proj_parts / 1e9))
print("  当前可用                  : %.1f GB" % (total.free / 1e9))
print("  交付后预计可用            : %.1f GB" % ((total.free - 2 * proj_parts) / 1e9))
print("  结论:", "充足" if total.free - 2 * proj_parts > 20e9 else "偏紧，需要在合并后删除 parts")
PYEOF
echo
echo "=== 可回收的彩排脚手架 ==="
for d in "$RUN/rehearsal/scale30" "$RUN/rehearsal/parallel" "$RUN/rehearsal/parallel2" "$RUN/rehearsal/reconcile_check" "$RUN/rehearsal/memcheck.sh" "$RUN/rehearsal/consolidated_check.parquet"; do
  [ -e "$d" ] && echo "  $(du -sh "$d" 2>/dev/null | cut -f1)  $d"
done
echo
echo "=== pool 与守护 ==="
echo "  oos 完成: $(ls $RUN/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l) / 213"
ps -eo pid,etime,args | awk '/run_one_shard\.sh [0-9]|retain_passing_values|mirror_runtime/ && !/awk/ {print "  " $1, $2, substr($0, index($0,$3), 60)}'
date -Is
