RUN=/home/data/agentmatrix_run
echo "=== 磁盘现状 ==="
df -h / | awk 'NR==2{print "  可用 "$4" / "$2" 已用 "$5}'
echo
echo "=== 占用前 10 ==="
du -sh "$RUN"/* 2>/dev/null | sort -hr | head -10 | sed 's/^/  /'
echo
echo "=== 外部 dry-run 的增长（与它的最终规模判断）==="
SZ=$(du -sb "$RUN/delivery_dryrun" 2>/dev/null | cut -f1)
echo "  当前: $(echo "$SZ/1000000000" | bc -l | cut -c1-5) GB"
echo "  其内容:"
du -sh "$RUN/delivery_dryrun"/* 2>/dev/null | sed 's/^/    /'
echo "  重建的因子数（由 batch_manifest 计）: $(/home/data/conda-envs/rqsdk/bin/python -X utf8 -c "
import json
try:
    m=json.load(open('$RUN/delivery_dryrun/merged/batch_manifest.json'))
    rs=m.get('results',[])
    print(sum(1 for r in rs if r.get('status')=='validated' and not r.get('failed_gates')))
except Exception as e:
    print('读取失败', e)
")"
echo
echo "=== 我方可回收的残留 ==="
for d in "$RUN/rehearsal/scale30" "$RUN/rehearsal/scale50" "$RUN/rehearsal/scale60" \
         "$RUN/rehearsal/parallel" "$RUN/rehearsal/parallel2" "$RUN/rehearsal/wd_verify" \
         "$RUN/rehearsal/watchdog_test" "$RUN/rehearsal/watchdog_test2" "$RUN/rehearsal/watchdog_test3" \
         "$RUN/scratch" "$RUN/delivery/rebuild" "$RUN/ref"; do
  [ -e "$d" ] && echo "  $(du -sh "$d" 2>/dev/null | cut -f1)  $d"
done
echo
echo "=== 交付期磁盘需求 ==="
PARTS=$(du -sb "$RUN/delivery/values/parts" 2>/dev/null | cut -f1)
NEED=$((PARTS * 12 / 10))   # 合并文件与 parts 同量级，留 20% 余量
printf "  当前 parts: %.1f GB\n" "$(echo "$PARTS/1000000000" | bc -l)"
printf "  合并文件需要: 约 %.1f GB\n" "$(echo "$NEED/1000000000" | bc -l)"
FREE=$(df -B1 / | awk 'NR==2{print $4}')
printf "  可用: %.1f GB → 扣除合并后剩 %.1f GB\n" "$(echo "$FREE/1000000000" | bc -l)" "$(echo "($FREE-$NEED)/1000000000" | bc -l)"
date -Is
