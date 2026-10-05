RUN=/home/data/agentmatrix_run
echo "--- 已完成 oos 的分片数 ---"
ls "$RUN"/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l
echo "--- 已完成 train 的分片数 ---"
ls "$RUN"/shards/shard*/train/batch_manifest.json 2>/dev/null | wc -l
echo "--- 驱动日志尾部 ---"
tail -5 "$RUN/logs/sharded_driver.log"
echo
echo "--- 前 3 个分片日志 ---"
for i in 00 01 02; do
  f="$RUN/logs/shard$i.log"
  echo "== shard$i (${i}) =="
  tail -3 "$f" 2>/dev/null | cut -c1-100
done
echo
echo "--- 正在跑的进程 ---"
ps -eo pid,etime,rss,args | grep -E "[b]uild_factor|[v]alidate-batch" | cut -c1-90
echo
echo "--- 资源 ---"
free -g | head -2
uptime
df -h / | tail -1
