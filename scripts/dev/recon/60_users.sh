echo "===== 按用户汇总 CPU 与内存 ====="
ps -eo user,pcpu,rss,args --no-headers | awk '
{ u=$1; cpu[u]+=$2; mem[u]+=$3; n[u]++ }
END { printf "%-16s %8s %10s %6s\n", "USER", "CPU%", "RSS(GB)", "PROCS"
      for (x in cpu) printf "%-16s %8.1f %10.2f %6d\n", x, cpu[x], mem[x]/1048576, n[x] }' | sort -k3 -rn | head -20

echo
echo "===== 内存占用前 20 的进程 ====="
ps -eo pid,user,pcpu,pmem,rss,etime,args --sort=-rss --no-headers | head -20 | \
  awk '{printf "  %-8s %-14s cpu=%-5s rss=%6.2fGB up=%-12s %s\n", $1, $2, $3, $5/1048576, $6, substr($0, index($0,$7), 70)}'

echo
echo "===== 监听端口的服务 ====="
ss -tlnp 2>/dev/null | head -25

echo
echo "===== systemd 服务（运行中，非系统必需） ====="
systemctl list-units --type=service --state=running --no-pager --no-legend 2>/dev/null | awk '{print "  "$1}' | head -25

echo
echo "===== docker 容器 ====="
docker ps --format '  {{.Names}}  {{.Status}}  {{.Image}}' 2>/dev/null | head -10

echo
echo "===== pick 一下：谁在真正吃 CPU（近 1 分钟活跃） ====="
ps -eo pid,user,pcpu,etime,args --sort=-pcpu --no-headers | head -12 | \
  awk '{printf "  %-8s %-14s cpu=%-5s up=%-12s %s\n", $1, $2, $3, $4, substr($0, index($0,$5), 65)}'

echo
free -g | head -2
uptime
