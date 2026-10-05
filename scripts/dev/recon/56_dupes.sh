echo "--- pool / shard / xargs 进程 ---"
ps -eo pid,ppid,etime,args | grep -E "[r]un_pool|[r]un_one_shard|[x]args" | cut -c1-110
echo
echo "--- build 进程 ---"
ps -eo pid,etime,rss,args | grep "[b]uild_factor_values" | awk '{printf "  %s etime=%s rss=%.1fGB\n", $1, $2, $3/1048576}'
echo
echo "--- validate 进程 ---"
ps -eo pid,etime,rss,args | grep "[v]alidate-batch" | awk '{printf "  %s etime=%s rss=%.1fGB\n", $1, $2, $3/1048576}'
echo
echo "--- 分片目录 ---"
ls -d /home/data/agentmatrix_run/shards/shard* 2>/dev/null | wc -l
echo "--- 资源 ---"
free -g | head -2
uptime
date -Is
