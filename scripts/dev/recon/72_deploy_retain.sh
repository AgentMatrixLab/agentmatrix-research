RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
PY=/home/data/conda-envs/rqsdk/bin/python
MARK=mark_8f31_retain_guard

echo "=== 1. 一次性运行（验证语法与逻辑）==="
$PY -X utf8 "$RUN/retain_passing_values.py" --repo "$REPO" --once 2>&1 | tail -30

echo
echo "=== 2. 再跑一次（settle 逻辑应已稳定，可能开始链接）==="
sleep 3
$PY -X utf8 "$RUN/retain_passing_values.py" --repo "$REPO" --once 2>&1 | tail -20

echo
echo "=== 3. 启动常驻守护 ==="
EXISTING=$(ps -eo pid,args | awk -v m="$MARK" '$0 !~ m && /retain_passing_values\.py/ && /interval/ {print $1}')
for pid in $EXISTING; do echo "  停掉旧守护 $pid"; kill -TERM "$pid" 2>/dev/null; done
sleep 2
setsid nohup $PY -X utf8 "$RUN/retain_passing_values.py" --repo "$REPO" --interval 20 \
  > "$RUN/logs/retain_daemon.log" 2>&1 < /dev/null &
sleep 6
echo "--- retain_daemon.log ---"
tail -10 "$RUN/logs/retain_daemon.log" 2>/dev/null

echo
echo "=== 4. 守护进程确认 ==="
ps -eo pid,etime,args | awk -v m="$MARK" '$0 !~ m && /retain_passing_values/ {print "  " $1, $2, $4, $5, $6, $7}'

echo
echo "=== 5. 当前留存状态 ==="
cat "$RUN/delivery/values/retain_status.json" 2>/dev/null
echo
echo "  raw 链接数: $(ls $RUN/delivery/values/raw/*.parquet 2>/dev/null | wc -l)"
echo "  parts 数  : $(ls $RUN/delivery/values/parts/*.parquet 2>/dev/null | wc -l)"
ls -la $RUN/delivery/values/raw/ 2>/dev/null | head -8

echo
echo "=== 6. pool 进度 ==="
echo "  oos 完成: $(ls $RUN/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l) / 213"
echo "  构建报告: $(ls $RUN/shards/shard*/build_report.json 2>/dev/null | wc -l)"
ps -eo pid,etime,args | awk '/run_one_shard\.sh [0-9]/ {print "  pid=" $1, "etime=" $2, "shard=" $NF}'
echo
echo "  磁盘: $(df -h / | awk 'NR==2{print $4" 可用 / "$2" 总"}')"
free -g | head -2
date -Is
