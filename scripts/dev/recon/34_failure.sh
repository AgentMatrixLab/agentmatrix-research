echo "===== shard00 完整日志 ====="
cat /home/data/agentmatrix_run/logs/shard00.log
echo
echo "===== shard05 尾部 ====="
tail -25 /home/data/agentmatrix_run/logs/shard05.log
echo
echo "===== 磁盘 ====="
df -h / | tail -1
