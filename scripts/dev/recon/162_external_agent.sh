RUN=/home/data/agentmatrix_run
echo "=== 外部 agent 的 dry-run 是否在跑 ==="
ps -eo pid,pcpu,etime,rss,args --sort=-pcpu | awk '/rebuild_passing_factors|delivery_dryrun|70_dryrun/ && !/awk/ {printf "  cpu=%s%% etime=%s rss=%.1fGB %s\n", $2, $3, $4/1048576, substr($0, index($0,$5), 90)}'
echo "  （空 = 未运行）"
echo
echo "=== delivery_dryrun 目录状态 ==="
if [ -d "$RUN/delivery_dryrun" ]; then
  du -sh "$RUN/delivery_dryrun" 2>/dev/null | sed 's/^/  占用 /'
  find "$RUN/delivery_dryrun" -maxdepth 2 -type f 2>/dev/null | head -8 | sed 's/^/    /'
  echo "  最后修改: $(find "$RUN/delivery_dryrun" -type f -printf '%TY-%Tm-%Td %TH:%TM %p\n' 2>/dev/null | sort | tail -1)"
else
  echo "  目录不存在 —— 从未运行过"
fi
echo
echo "=== 关键判断：真实交付链会不会走 rebuild 这条路？ ==="
OOS=$(ls $RUN/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l)
PARTS=$(ls $RUN/delivery/values/parts/*.parquet 2>/dev/null | wc -l)
echo "  oos=$OOS  parts=$PARTS"
if [ "$PARTS" -ge "$OOS" ]; then
  echo "  ⇒ parts >= oos，链条走「合并留存 parts」分支；rebuild_passing_factors 在真实交付时【根本不会被调用】"
  echo "  ⇒ 该 dry-run 演练的是一条交付时不会执行、且代价最高（重建全部通过因子）的路径"
else
  echo "  ⇒ 当前 parts < oos，链条【会】走 rebuild 分支"
fi
echo
echo "=== 当前 CPU 前 8（看是否有人在抢分片的 CPU）==="
ps -eo pcpu,etime,args --sort=-pcpu | head -9 | cut -c1-110 | sed 's/^/  /'
echo
echo "=== 分片速率是否受影响（最近 6 个完成）==="
for f in "$RUN"/logs/shard*.log; do
  d=$(grep -o '### shard[0-9]* done [0-9T:+-]*' "$f" 2>/dev/null | head -1 | awk '{print $4}')
  t=$(basename "$f" .log)
  [ -n "$d" ] && echo "$d $t"
done | sort | tail -6 | sed 's/^/  /'
date -Is
