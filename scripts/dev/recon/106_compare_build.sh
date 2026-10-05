RUN=/home/data/agentmatrix_run
for i in 020 021 022 023 024; do
  f="$RUN/logs/shard$i.log"
  [ -f "$f" ] || continue
  echo "=== shard$i ==="
  head -8 "$f" | sed 's/^/   /'
  echo
done
echo "=== 对照：candidates 数与 keep_columns ==="
grep -h 'panel columns kept' "$RUN"/logs/shard02*.log | sed 's/^/  /'
echo
echo "=== 每个分片的候选（确认 023/024 的公式是否特殊）==="
for i in 022 023 024; do
  d="$RUN/shards/shard$i"
  [ -f "$d/candidate_list.csv" ] || continue
  echo "  --- shard$i"
  /home/data/conda-envs/rqsdk/bin/python -X utf8 - "$d/candidate_list.csv" <<'PYEOF'
import csv, sys
for r in csv.DictReader(open(sys.argv[1], encoding="utf-8")):
    print("     %-28s window=%-4s formula=%s" % (
        r.get("factor_id"), r.get("window"), (r.get("formula") or "")[:60]))
PYEOF
done
date -Is
