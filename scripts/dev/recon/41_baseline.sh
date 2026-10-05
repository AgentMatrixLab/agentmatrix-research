#!/usr/bin/env bash
echo "===== 我的进程是否清空 ====="
ps -eo pid,args | grep -E "[b]uild_factor|[v]alidate-batch|[r]un_sharded" | cut -c1-80
echo "(空即正确)"

echo
echo "===== 负载趋势（每 10 秒） ====="
for i in 1 2 3 4 5 6; do
  printf "  t+%02ds  %s\n" $((i*10)) "$(uptime | sed 's/.*load average: //')"
  sleep 10
done

echo
echo "===== 别人在跑什么（按内存） ====="
ps -eo pid,user,pcpu,pmem,rss,etime,args --sort=-rss | head -12 | cut -c1-140

echo
echo "===== 内存 / 交换 ====="
free -g
swapon --show
echo
echo "===== CPU 核数 vs 当前可跑 ====="
nproc
echo "  1 分钟负载: $(uptime | sed 's/.*average: //' | cut -d, -f1)"

echo
echo "===== 磁盘 ====="
df -h / | tail -1

echo
echo "===== 我的分片目录现状 ====="
ls -d /home/data/agentmatrix_run/shards/shard* 2>/dev/null | wc -l
du -sh /home/data/agentmatrix_run/shards 2>/dev/null
ls /home/data/agentmatrix_run/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l
echo "  ^ 已完成的 oos 分片数"
