pkill -f run_sharded.sh 2>/dev/null
sleep 2
pkill -f build_factor_values.py 2>/dev/null
sleep 3
echo "--- 残留进程 ---"
ps -eo pid,args | grep -E "build_factor|run_sharded|validate-batch" | grep -v grep | cut -c1-90
echo "--- 内存 ---"
free -g | head -2
