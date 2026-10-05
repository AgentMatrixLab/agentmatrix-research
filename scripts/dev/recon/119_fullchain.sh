RUN=/home/data/agentmatrix_run
OUT=$RUN/rehearsal/fullchain.log
cat > "$RUN/rehearsal/fullchain.sh" <<'EOF'
#!/usr/bin/env bash
# Stop the pool, run the COMPLETE chain, restart the pool. Detached, so an SSH drop cannot
# kill it halfway and leave the pool stopped.
set -u
RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
STAMP=71760b4138e350338299a6f48f269099ebbfab5c
MARK=mark_fullchain_guard

echo "########## 0. 前置 ##########"
echo "  oos 完成: $(ls $RUN/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l)"
echo "  parts   : $(ls $RUN/delivery/values/parts/*.parquet 2>/dev/null | wc -l)"
echo "  磁盘可用: $(df -h / | awk 'NR==2{print $4}')"
echo "  内存可用: $(free -g | awk '/^Mem:/{print $7}')GB"
echo "  start $(date -Is)"

echo
echo "########## 1. 安全停止 pool（按进程组，绝不按模式）##########"
POOL_PID=$(ps -eo pid,args | awk -v m="$MARK" '$0 !~ m && /run_pool\.sh/ {print $1; exit}')
if [ -z "$POOL_PID" ]; then
  echo "  未找到 pool"
else
  PGID=$(ps -o pgid= -p "$POOL_PID" | tr -d ' ')
  MYPGID=$(ps -o pgid= -p $$ | tr -d ' ')
  echo "  pool pid=$POOL_PID pgid=$PGID 本shell pgid=$MYPGID"
  if [ "$PGID" = "$MYPGID" ]; then echo "  中止：同进程组"; exit 1; fi
  kill -TERM -"$PGID" 2>/dev/null
  sleep 10
  LEFT=$(ps -eo pid,pgid,args | awk -v p="$PGID" -v m="$MARK" '$0 !~ m && $2 == p {c++} END {print c+0}')
  echo "  剩余 $LEFT"
  [ "$LEFT" -gt 0 ] && kill -KILL -"$PGID" 2>/dev/null
fi
sleep 3
echo "  残留分片进程: $(ps -eo args | awk -v m="$MARK" '$0 !~ m && /run_one_shard\.sh [0-9]/ {c++} END {print c+0}')"
echo "  内存可用: $(free -g | awk '/^Mem:/{print $7}')GB  （pool 停后应显著回升）"

echo
echo "########## 2. 完整链（0→1→2→2b→3→4a→4b→5→7→8→9）##########"
cd "$REPO" || exit 1
export PYTHONPATH="$REPO"
sed -i 's/\r$//' scripts/dev/run_downstream.sh
bash scripts/dev/run_downstream.sh "$RUN"
echo "CHAIN exit=$?"

echo
echo "########## 3. 重启 pool（pinned stamp，跳过已完成分片）##########"
cd "$REPO" || exit 1
setsid nohup env AGENTMATRIX_COMMIT="$STAMP" bash "$REPO/scripts/dev/run_pool.sh" 213 2 \
  > "$RUN/logs/pool_run4.log" 2>&1 < /dev/null &
sleep 30
head -6 "$RUN/logs/pool_run4.log"
echo "  在跑: $(ps -eo args | awk -v m="$MARK" '$0 !~ m && /run_one_shard\.sh [0-9]/ {c++} END {print c+0}')"
echo "########## 结束 $(date -Is) ##########"
EOF
sed -i 's/\r$//' "$RUN/rehearsal/fullchain.sh"
chmod +x "$RUN/rehearsal/fullchain.sh"
setsid nohup bash "$RUN/rehearsal/fullchain.sh" > "$OUT" 2>&1 < /dev/null &
echo "  已启动完整链验证（detached，预计约 50 分钟）"
date -Is
