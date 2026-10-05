RUN=/home/data/agentmatrix_run
PY=/home/data/conda-envs/rqsdk/bin/python
MARK=mark_5e12_mirror_guard

echo "=== 已有 mirror 守护进程？（用 ps 精确匹配，不用 pkill -f）==="
EXISTING=$(ps -eo pid,args | awk -v m="$MARK" '$0 !~ m && /mirror_runtime_data\.py/ && /interval/ {print $1}')
echo "  已存在: ${EXISTING:-无}"
for pid in $EXISTING; do
  echo "  停掉旧守护 pid=$pid"
  kill -TERM "$pid" 2>/dev/null
done
sleep 2

echo
echo "=== 启动常驻守护 ==="
setsid nohup $PY -X utf8 "$RUN/mirror_runtime_data.py" --interval 60 \
  > "$RUN/logs/mirror.log" 2>&1 < /dev/null &
sleep 10
echo "--- mirror.log ---"
tail -5 "$RUN/logs/mirror.log"

echo
echo "=== 校验 ==="
SRC=$RUN/agentmatrix/data/factor_lab/validation_runs
DST=$RUN/runtime_mirror/data/factor_lab/validation_runs
echo "  源  validation_result.json : $(find $SRC -name validation_result.json 2>/dev/null | wc -l)"
echo "  镜像 validation_result.json : $(find $DST -name validation_result.json 2>/dev/null | wc -l)"
echo "  源  总文件 : $(find $SRC -type f 2>/dev/null | wc -l)"
echo "  镜像 总文件 : $(find $DST -type f 2>/dev/null | wc -l)"
echo
echo "  --- 抽查 3 个文件的 md5 是否一致 ---"
for f in $(find $SRC -name validation_result.json 2>/dev/null | head -3); do
  rel=${f#$SRC/}
  a=$(md5sum "$f" | cut -d' ' -f1)
  b=$(md5sum "$DST/$rel" 2>/dev/null | cut -d' ' -f1)
  if [ "$a" = "$b" ]; then echo "    一致  $rel"; else echo "    不一致 $rel  src=$a dst=$b"; fi
done

echo
echo "=== 守护进程确认 ==="
ps -eo pid,etime,args | awk -v m="$MARK" '$0 !~ m && /mirror_runtime_data/ {print "  " $1, $2, $4, $5, $6, $7}'
echo
echo "=== pool 进度 ==="
echo "  oos 完成: $(ls $RUN/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l) / 213"
ps -eo pid,etime,args | awk '/run_one_shard\.sh [0-9]/ {print "  " $1, $2, $4}'
date -Is
