#!/usr/bin/env bash
# Re-split the candidates and drive the shards with a plain worker pool.
#
# Replaces the `wait -n` driver, which was measured running one shard at a time.
set -u

RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
PY=/home/data/conda-envs/rqsdk/bin/python
SHARDS=${1:-213}
PARALLEL=${2:-3}
LOGS=$RUN/logs

cd "$REPO" || exit 1
export PYTHONPATH="$REPO"
mkdir -p "$LOGS" "$RUN/shards"

echo "=== 切分 $SHARDS 片（保留已完成的结果） ==="
"$PY" -X utf8 - "$SHARDS" <<'PYEOF'
import csv, os, sys
shards = int(sys.argv[1])
run = "/home/data/agentmatrix_run"
rows = list(csv.DictReader(open(run + "/candidate_list.csv", encoding="utf-8")))
buckets = [[] for _ in range(shards)]
for i, row in enumerate(rows):
    buckets[i % shards].append(row)
fields = list(rows[0])
written = skipped = 0
for i, bucket in enumerate(buckets):
    target = run + "/shards/shard%03d" % i
    os.makedirs(target, exist_ok=True)
    # Do not redo a shard whose oos result already exists.
    if os.path.exists(target + "/oos/batch_manifest.json"):
        skipped += 1
        continue
    with open(target + "/candidate_list.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(bucket)
    written += 1
print("  待跑 %d 片，已有结果跳过 %d 片" % (written, skipped))
PYEOF

# Only hand xargs the shards that still need work.
TODO=$RUN/logs/todo.txt
: > "$TODO"
for d in "$RUN"/shards/shard*/; do
  tag=$(basename "$d")
  [ -f "$d/oos/batch_manifest.json" ] && continue
  echo "${tag#shard}" >> "$TODO"
done
COUNT=$(wc -l < "$TODO")
echo "  实际入队: $COUNT 片，并行 $PARALLEL"

if [ "$COUNT" -eq 0 ]; then
  echo "  没有待跑分片"
  exit 0
fi

echo "=== 启动 worker pool ==="
START=$(date +%s)
cat "$TODO" | xargs -P "$PARALLEL" -n 1 -I{} bash "$REPO/scripts/dev/run_one_shard.sh" {}
END=$(date +%s)
echo
echo "=== 全部完成，用时 $(( (END - START) / 60 )) 分钟 ==="
echo "  oos 完成: $(ls $RUN/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l)"
