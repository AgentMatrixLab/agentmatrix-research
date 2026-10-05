RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
STAMP=71760b4138e350338299a6f48f269099ebbfab5c
MARK=mark_b7c41e_killguard

echo "=== 0. 前置检查 ==="
echo "  服务器 COMMIT 文件 : $(cat $REPO/COMMIT 2>/dev/null)"
echo "  将 pin 的 stamp     : $STAMP"
echo "  commit 长度         : ${#STAMP}"

echo
echo "=== 1. 保存第一轮 manifest 作为确定性对照（重跑后可比对判决是否逐一相同）==="
mkdir -p "$RUN/reference/run1/manifests"
n=0
for d in "$RUN"/shards/shard*/; do
  tag=$(basename "$d")
  if [ -f "$d/oos/batch_manifest.json" ]; then
    mkdir -p "$RUN/reference/run1/manifests/$tag"
    cp "$d/oos/batch_manifest.json" "$RUN/reference/run1/manifests/$tag/oos.json"
    [ -f "$d/train/batch_manifest.json" ] && cp "$d/train/batch_manifest.json" "$RUN/reference/run1/manifests/$tag/train.json"
    n=$((n + 1))
  fi
done
echo "  已保存 $n 个分片的 manifest -> $RUN/reference/run1/manifests"

echo
echo "=== 2. 移开 shard000-009（它们记录的 code_commit 是短哈希，与新 pin 不一致）==="
for i in 000 001 002 003 004 005 006 007 008 009; do
  if [ -d "$RUN/shards/shard$i" ]; then
    rm -rf "$RUN/reference/run1/shard${i}_run1"
    mv "$RUN/shards/shard$i" "$RUN/reference/run1/shard${i}_run1"
    echo "  移开 shard$i"
  fi
done

echo
echo "=== 3. 停止当前 worker pool（按进程组，避免误杀本 shell）==="
POOL_PID=$(ps -eo pid,args | awk -v m="$MARK" '$0 !~ m && /run_pool\.sh 213/ {print $1; exit}')
if [ -z "$POOL_PID" ]; then
  echo "  未找到 run_pool.sh 进程（可能已退出）"
else
  PGID=$(ps -o pgid= -p "$POOL_PID" | tr -d ' ')
  MYPID=$$
  MYPGID=$(ps -o pgid= -p "$MYPID" | tr -d ' ')
  echo "  pool pid=$POOL_PID pgid=$PGID  本 shell pid=$MYPID pgid=$MYPGID"
  if [ "$PGID" = "$MYPGID" ]; then
    echo "  中止：pool 与本 shell 同进程组，不敢按组杀"
    exit 1
  fi
  kill -TERM -"$PGID" 2>/dev/null
  sleep 8
  LEFT=$(ps -eo pid,pgid,args | awk -v p="$PGID" -v m="$MARK" '$0 !~ m && $2 == p {c++} END {print c+0}')
  echo "  进程组 $PGID 剩余进程: $LEFT"
  if [ "$LEFT" -gt 0 ]; then
    echo "  仍有残留，补 SIGKILL"
    kill -KILL -"$PGID" 2>/dev/null
    sleep 3
  fi
fi

echo
echo "  残留的 run_one_shard 进程（应为空）:"
ps -eo pid,args | awk -v m="$MARK" '$0 !~ m && /run_one_shard\.sh/ {print "    " $0}'

echo
echo "=== 4. 以 pin 的 stamp 重启 pool ==="
cd "$REPO" || exit 1
setsid nohup env AGENTMATRIX_COMMIT="$STAMP" bash "$REPO/scripts/dev/run_pool.sh" 213 2 \
  > "$RUN/logs/pool_run2.log" 2>&1 < /dev/null &
sleep 25

echo "  pool_run2.log:"
sed 's/^/    /' "$RUN/logs/pool_run2.log" | head -20

echo
echo "=== 5. 校验 stamp 真的传到了子进程 ==="
for p in $(ps -eo pid,args | awk -v m="$MARK" '$0 !~ m && /build_factor_values/ {print $1}'); do
  got=$(tr '\0' '\n' < "/proc/$p/environ" 2>/dev/null | grep '^AGENTMATRIX_COMMIT=' | head -1)
  echo "    pid $p -> ${got:-（未设置）}"
done

echo
echo "=== 6. 当前进程树 ==="
ps -eo pid,ppid,etime,rss,args | awk -v m="$MARK" '$0 !~ m && (/run_pool/ || /run_one_shard/ || /xargs -P/) {print "    " $0}'
date -Is
