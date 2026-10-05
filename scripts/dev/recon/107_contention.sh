echo "=== 负载与 CPU ==="
uptime
echo
echo "=== 内存 ==="
free -g | head -2
echo
echo "=== 最近 1 分钟 CPU 占用前 15 ==="
ps -eo pid,ppid,pcpu,pmem,etime,rss,user,args --sort=-pcpu | head -16 | cut -c1-150
echo
echo "=== 我们自己的进程 ==="
ps -eo pid,pcpu,pmem,etime,rss,args --sort=-pcpu | awk '/run_one_shard|build_factor_values|validate-batch|retain_passing|mirror_runtime/ && !/awk/ {printf "  cpu=%s%% mem=%s%% etime=%s rss=%.1fGB %s\n", $2, $3, $4, $5/1048576, substr($0, index($0,$6), 80)}'
echo
echo "=== 各核占用（mpstat 若可用）==="
command -v mpstat >/dev/null && mpstat 1 2 | tail -4 || echo "  mpstat 不可用"
echo
echo "=== 磁盘 IO（iostat 若可用）==="
command -v iostat >/dev/null && iostat -x 1 2 | tail -12 || echo "  iostat 不可用"
echo
echo "=== 当前 shard 阶段 ==="
for i in 023 024; do
  echo "  --- shard$i"
  grep -E 'start |build wall|train wall|oos wall|done ' /home/data/agentmatrix_run/logs/shard$i.log 2>/dev/null | sed 's/^/     /'
done
date -Is
