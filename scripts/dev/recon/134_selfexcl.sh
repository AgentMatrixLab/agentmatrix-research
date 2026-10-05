RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
SB=$RUN/rehearsal/watchdog_test3
OUT=$RUN/rehearsal/wd3.log
echo "=== 本地语法自查（用真实 bash 语义）==="
bash -n "$REPO/scripts/dev/pool_watchdog.sh" && echo "  bash -n OK"
echo
echo "=== 自排除的语义测试：在沙箱里放一个含 marker 的假进程，看是否被正确识别 ==="
mkdir -p "$SB"
# 直接测试 awk 表达式本身：模拟 ps 输出
printf '%s\n' \
  "  100 bash /x/pool_watchdog.sh --run /y --pool-marker wd_marker" \
  "  200 bash /home/data/agentmatrix_run/agentmatrix/scripts/dev/run_pool.sh 213 2" \
  "  300 bash /y/agentmatrix/scripts/dev/run_pool.sh 5 2" \
  | awk -v me="999" -v pat="run_pool.sh" '$1 != me && $0 !~ /pool_watchdog\.sh/ && index($0, pat) > 0 {c++} END {print "  含 run_pool.sh 且非 watchdog 的进程数: " c+0}'
printf '%s\n' \
  "  100 bash /x/pool_watchdog.sh --run /y --pool-marker wd_marker" \
  "  200 bash /home/data/agentmatrix_run/agentmatrix/scripts/dev/run_pool.sh 213 2" \
  | awk -v me="999" -v pat="wd_marker" '$1 != me && $0 !~ /pool_watchdog\.sh/ && index($0, pat) > 0 {c++} END {print "  含 wd_marker 且非 watchdog 的进程数: " c+0 " (应为 0——watchdog 自己不算)"}'
date -Is
