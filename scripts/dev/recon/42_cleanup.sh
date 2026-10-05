#!/usr/bin/env bash
echo "===== 残留进程 ====="
ps -eo pid,args | grep -E "[b]uild_factor|[v]alidate-batch|[r]un_sharded" | cut -c1-90
echo "(空即正确)"

echo
echo "===== 清理分片目录 ====="
BEFORE=$(df -h / | awk 'NR==2{print $4}')
rm -rf /home/data/agentmatrix_run/shards /home/data/agentmatrix_run/memtest \
       /home/data/agentmatrix_run/tiny /home/data/agentmatrix_run/pilot
mkdir -p /home/data/agentmatrix_run/shards /home/data/agentmatrix_run/logs
AFTER=$(df -h / | awk 'NR==2{print $4}')
echo "  磁盘: $BEFORE -> $AFTER"

echo
echo "===== 确认代码是修复后的版本 ====="
cd /home/data/agentmatrix_run/agentmatrix || exit 1
echo -n "  precomputed_factors.py 里 categorical 出现次数: "
grep -c "category" research_core/factor_lab/precomputed_factors.py
echo -n "  run_sharded.sh 里 wait_for_memory 出现次数: "
grep -c "wait_for_memory" scripts/dev/run_sharded.sh
echo -n "  build_factor_values.py 里 emit-start: "
grep -c "emit-start" scripts/build_factor_values.py

echo
echo "===== 当前负载与内存（基线） ====="
uptime
free -g | head -2
