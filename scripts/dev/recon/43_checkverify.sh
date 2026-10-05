echo "--- 内存验证脚本还在跑吗 ---"
ps -eo pid,etime,args | grep -E "[v]erify_loader|[b]uild_factor|[p]recomputed" | cut -c1-130
echo
echo "--- memtest 目录 ---"
ls -la /home/data/agentmatrix_run/memtest 2>/dev/null
echo
echo "--- 负载 ---"
uptime
echo
echo "--- 内存 ---"
free -g | head -2
