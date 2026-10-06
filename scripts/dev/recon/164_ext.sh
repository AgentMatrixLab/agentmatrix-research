RUN=/home/data/agentmatrix_run
echo "=== 外部 agent 的 rebuild ==="
ps -eo etime,pcpu,rss,args | grep -E 'rebuild_passing_factors' | grep -v grep | head -3 | cut -c1-100 | sed 's/^/  /'
echo "  dryrun 目录: $(du -sh $RUN/delivery_dryrun 2>/dev/null | cut -f1)"
echo "  最后写入  : $(find $RUN/delivery_dryrun -type f -printf '%TH:%TM %p\n' 2>/dev/null | sort | tail -1)"
echo
echo "=== 分片与资源 ==="
echo "  已完成: $(ls $RUN/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l) / 213"
echo "  磁盘可用: $(df -h / | awk 'NR==2{print $4}')"
echo "  内存可用: $(free -g | awk '/^Mem:/{print $7}')GB"
echo "  在跑分片: $(ps -eo args | awk '/run_one_shard\.sh [0-9]/ && !/awk/ {c++} END {print c+0}')"
date -Is
