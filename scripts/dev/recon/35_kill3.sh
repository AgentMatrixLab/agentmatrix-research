#!/usr/bin/env bash
for pid in $(ps -eo pid,args | grep -E "[r]un_sharded.sh|[b]uild_factor_values.py|[v]alidate-batch" | awk '{print $1}'); do
  kill -TERM "$pid" 2>/dev/null
done
sleep 4
for pid in $(ps -eo pid,args | grep -E "[r]un_sharded.sh|[b]uild_factor_values.py|[v]alidate-batch" | awk '{print $1}'); do
  kill -KILL "$pid" 2>/dev/null
done
sleep 3
echo "--- 残留 ---"
ps -eo pid,args | grep -E "[b]uild_factor|[r]un_sharded|[v]alidate-batch" | cut -c1-80
echo "--- 清掉失败分片的因子文件（保留 build_report 与结果） ---"
BEFORE=$(df -h / | awk 'NR==2{print $4}')
rm -f /home/data/agentmatrix_run/shards/*/factor_values.parquet
rm -rf /home/data/agentmatrix_run/tiny /home/data/agentmatrix_run/pilot
AFTER=$(df -h / | awk 'NR==2{print $4}')
echo "  磁盘可用: $BEFORE -> $AFTER"
echo "--- 内存 ---"
free -g | head -2
