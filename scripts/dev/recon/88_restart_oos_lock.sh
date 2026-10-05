RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
PY=/home/data/conda-envs/rqsdk/bin/python
STAMP=71760b4138e350338299a6f48f269099ebbfab5c
MARK=mark_7d40_pool_restart

echo "=== 1. 前置检查 ==="
command -v flock >/dev/null && echo "  flock: $(command -v flock)" || echo "  flock 缺失！"
grep -c 'flock' $REPO/scripts/dev/run_one_shard.sh
echo "  oos 串行化修复已就位（上面应为 3）"

echo
echo "=== 2. 记录当前失败分片（无 manifest 且不在飞行中的）==="
/home/data/conda-envs/rqsdk/bin/python -X utf8 - <<'PYEOF'
import glob, os, json, re
run = "/home/data/agentmatrix_run"
done = set()
for p in glob.glob(run + "/shards/shard*/oos/batch_manifest.json"):
    done.add(os.path.basename(os.path.dirname(os.path.dirname(p))))
oos_failed = []
for f in glob.glob(run + "/logs/shard*.log"):
    tag = os.path.basename(f)[:-4]
    txt = open(f, encoding="utf-8", errors="ignore").read()
    if "signal 9" in txt or "OOS FAILED" in txt or "TRAIN FAILED" in txt or "BUILD FAILED" in txt:
        oos_failed.append(tag)
print("  已完成:", len(done))
print("  日志里有失败标记:", sorted(oos_failed))
PYEOF

echo
echo "=== 3. 停止当前 pool（按进程组）==="
POOL_PID=$(ps -eo pid,args | awk -v m="$MARK" '$0 !~ m && /run_pool\.sh 213/ {print $1; exit}')
if [ -n "$POOL_PID" ]; then
  PGID=$(ps -o pgid= -p "$POOL_PID" | tr -d ' ')
  MYPGID=$(ps -o pgid= -p $$ | tr -d ' ')
  echo "  pool pid=$POOL_PID pgid=$PGID  本shell pgid=$MYPGID"
  if [ "$PGID" != "$MYPGID" ]; then kill -TERM -"$PGID" 2>/dev/null; sleep 8; fi
  LEFT=$(ps -eo pid,pgid,args | awk -v p="$PGID" -v m="$MARK" '$0 !~ m && $2 == p {c++} END {print c+0}')
  echo "  剩余: $LEFT"
  [ "$LEFT" -gt 0 ] && kill -KILL -"$PGID" 2>/dev/null
else
  echo "  未找到 pool"
fi
sleep 2
ps -eo pid,args | awk -v m="$MARK" '$0 !~ m && /run_one_shard|xargs -P/ {print "  残留: " $0}'

echo
echo "=== 4. 以 pin 的 stamp 重启 pool（会自动重排未完成分片，含 004/005）==="
cd "$REPO" || exit 1
sed -i 's/\r$//' scripts/dev/run_one_shard.sh scripts/dev/run_pool.sh
chmod +x scripts/dev/run_one_shard.sh scripts/dev/run_pool.sh
setsid nohup env AGENTMATRIX_COMMIT="$STAMP" bash "$REPO/scripts/dev/run_pool.sh" 213 2 \
  > "$RUN/logs/pool_run3.log" 2>&1 < /dev/null &
sleep 30
echo "--- pool_run3.log ---"
head -12 "$RUN/logs/pool_run3.log"
echo
echo "--- 运行中的 worker（注意 oos 串行化后两者相位应错开）---"
ps -eo pid,etime,args | awk -v m="$MARK" '$0 !~ m && /run_one_shard\.sh [0-9]/ {print "  pid=" $1, "etime=" $2, "arg=" $NF}'
echo
echo "  待跑分片数: $(wc -l < $RUN/logs/todo.txt 2>/dev/null)"
date -Is
