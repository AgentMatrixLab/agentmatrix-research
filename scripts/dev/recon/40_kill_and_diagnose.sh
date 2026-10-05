#!/usr/bin/env bash
echo "===== 杀掉我们自己起的一切 ====="
for pid in $(ps -eo pid,args | grep -E "[r]un_sharded.sh|[b]uild_factor_values.py|[v]alidate-batch" | awk '{print $1}'); do
  echo "  TERM $pid"
  kill -TERM "$pid" 2>/dev/null
done
sleep 5
for pid in $(ps -eo pid,args | grep -E "[r]un_sharded.sh|[b]uild_factor_values.py|[v]alidate-batch" | awk '{print $1}'); do
  echo "  KILL $pid"
  kill -KILL "$pid" 2>/dev/null
done
sleep 3

echo
echo "===== 为什么负载是 220？谁在吃 CPU ====="
ps -eo pid,ppid,pcpu,pmem,rss,etime,args --sort=-pcpu | head -15 | cut -c1-150

echo
echo "===== 负载 / 内存 / 交换 ====="
uptime
free -g
echo "--- swap 使用 ---"
swapon --show 2>/dev/null || echo "(无 swap?)"
echo "--- 阻塞在 IO 的进程数 ---"
ps -eo stat | grep -c "^D"

echo
echo "===== 线程数最多的进程 ====="
ps -eo pid,nlwp,pcpu,rss,args --sort=-nlwp | head -8 | cut -c1-120

echo
echo "===== 残留 ====="
ps -eo pid,args | grep -E "[b]uild_factor|[v]alidate-batch|[r]un_sharded" | cut -c1-80
echo "(空即为已清空)"
echo
df -h / | tail -1
