RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
STAMP=71760b4138e350338299a6f48f269099ebbfab5c

echo "=== 1. 把完整 40 位 SHA 写进 COMMIT 文件（防止任何重启回落到 7 位短哈希）==="
echo "  修改前: $(cat $REPO/COMMIT)"
echo "$STAMP" > "$REPO/COMMIT"
echo "  修改后: $(cat $REPO/COMMIT)"
echo "  长度  : $(wc -c < $REPO/COMMIT) （41 = 40 + 换行）"

echo
echo "=== 2. 确认运行中的 worker 仍用 pinned 环境变量 ==="
for p in $(ps -eo pid,args | awk '$0 !~ /awk/ && /build_factor_values|validate-batch/ {print $1}'); do
  got=$(tr '\0' '\n' < "/proc/$p/environ" 2>/dev/null | grep '^AGENTMATRIX_COMMIT=' | head -1)
  echo "  pid $p -> ${got:-（未设置，将回落到 COMMIT 文件 = $STAMP）}"
done

echo
echo "=== 3. 已完成分片的 code_commit 一致性 ==="
/home/data/conda-envs/rqsdk/bin/python -X utf8 - <<'PYEOF'
import glob, json, collections
c = collections.Counter()
for p in sorted(glob.glob("/home/data/agentmatrix_run/shards/shard*/oos/batch_manifest.json")):
    pl = json.load(open(p))
    c[pl.get("code_commit")] += 1
for k, v in c.items():
    print("  %s  x%d  (len=%d)" % (k, v, len(str(k))))
PYEOF

echo
echo "=== 4. 留存 daemon / mirror 是否仍在跑 ==="
ps -eo pid,etime,args | awk '/retain_passing_values|mirror_runtime_data/ && !/awk/ {print "  " $1, $2, $4, $5}'
echo "  parts: $(ls $RUN/delivery/values/parts/*.parquet 2>/dev/null | wc -l)   raw链接: $(ls $RUN/delivery/values/raw/*.parquet 2>/dev/null | wc -l)"
echo "  镜像 runs: $(find $RUN/runtime_mirror/data/factor_lab/validation_runs -name validation_result.json 2>/dev/null | wc -l)"

echo
echo "=== 5. pool 进度 ==="
echo "  oos 完成: $(ls $RUN/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l) / 213"
ps -eo pid,etime,args | awk '/run_one_shard\.sh [0-9]/ {print "    pid=" $1, "etime=" $2, "arg=" $NF}'
date -Is
