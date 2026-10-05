echo "--- report.json ---"
cat /home/data/agentmatrix_run/pilot/report.json 2>/dev/null
echo
echo "--- sidecar ---"
cat /home/data/agentmatrix_run/pilot/factor_values.parquet.json 2>/dev/null
echo
echo "--- 进程详情 ---"
ps -eo pid,ppid,stat,rss,etime,args | grep -E "build_factor|time -v" | grep -v grep | cut -c1-150
echo
echo "--- 文件时间 ---"
stat -c '%n  %s bytes  mtime=%y' /home/data/agentmatrix_run/pilot/* 2>/dev/null
echo
echo "--- 当前时间 ---"
date -Is
echo
echo "--- 打开的文件句柄 ---"
ls -l /proc/2994119/fd 2>/dev/null | head -5
cat /proc/2994119/status 2>/dev/null | grep -E "State|VmRSS|Threads"
