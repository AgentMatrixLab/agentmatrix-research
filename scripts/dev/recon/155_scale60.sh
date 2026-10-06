RUN=/home/data/agentmatrix_run
OUT=$RUN/rehearsal/scale60.log
cat > "$RUN/rehearsal/scale60.sh" <<'EOF'
#!/usr/bin/env bash
# Exercise the chain's first three heavy steps at close to the final scale, in a scratch dir so
# the pool keeps running. The supplementary layer is the one step whose memory was extrapolated
# from 29 factors rather than measured; it is also the step the demo follows, so knowing its real
# cost at ~137 factors is what makes the chain-time budget trustworthy.
set -u
RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
PY=/home/data/conda-envs/rqsdk/bin/python
W=$RUN/rehearsal/scale60
rm -rf "$W"; mkdir -p "$W"
cd $REPO || exit 1
export PYTHONPATH=$REPO
echo "start $(date -Is)  shards=$(ls $RUN/shards/shard*/oos/batch_manifest.json | wc -l)"

echo
echo "########## 1. 批次范围 + 合并 ##########"
$PY -X utf8 -u scripts/build_batch_candidates.py --run "$RUN" \
  --candidates "$RUN/candidate_list.csv" --output "$W/batch_candidates.csv" | tail -2
/usr/bin/time -f "  MERGE wall=%es maxrss=%MkB" $PY -X utf8 -u scripts/merge_batch_manifests.py \
  --shards $RUN/shards/shard*/oos/batch_manifest.json \
  --candidates "$W/batch_candidates.csv" --output-dir "$W/merged" \
  | $PY -X utf8 -c "
import json,sys
d=json.load(sys.stdin)
print('  shards=%s candidates=%s validated=%s' % (d['shard_count'], d['candidate_count'], d['counts']['validated']))
"

echo
echo "########## 2b. 合并因子值（60 个 parts）##########"
/usr/bin/time -f "  CONSOLIDATE wall=%es maxrss=%MkB" \
  $PY -X utf8 -u scripts/consolidate_factor_values.py \
    --parts "$RUN/delivery/values/parts" --output "$W/factor_values.parquet"
$PY -X utf8 -u - "$W/factor_values.parquet" <<'PYEOF'
import json, sys
from pathlib import Path
p = Path(sys.argv[1]); side = json.loads(Path(str(p) + ".json").read_text())
n = len(side["factors"]); rows = side["row_count"]
per = sorted({v["rows"] for v in side["factors"].values()})
print("  factors=%d rows=%s rows/series=%s" % (n, format(rows, ","), format(per[0], ",") if per else "-"))
print("  算术校验 %d x %s = %s == row_count → %s" % (
    n, format(per[0], ",") if per else "-", format(n * per[0], ",") if per else "-",
    "YES（无重复键）" if per and n * per[0] == rows else "NO"))
PYEOF

echo
echo "########## 3. 稳健性附加层（FDR + 行业中性留存）—— 本轮要测的规模 ##########"
/usr/bin/time -f "  SUPPLEMENT wall=%es maxrss=%MkB" \
  $PY -X utf8 -u scripts/run_robustness_supplement.py \
    --batch-manifest "$W/merged/batch_manifest.json" \
    --candidates "$RUN/candidate_list.csv" \
    --factor-values "$W/factor_values.parquet" \
    --config "$REPO/configs/validation_gates.yaml" \
    --out "$W/supplementary_report.json" --jobs 6
echo "  exit=$?"
$PY -X utf8 -u - "$W/supplementary_report.json" <<'PYEOF'
import json, sys
d = json.load(open(sys.argv[1]))
s = d.get("summary") or {}
m = d.get("marginal_effect") or {}
print("  summary :", json.dumps(s, ensure_ascii=False))
if m:
    print("  marginal:", json.dumps(m, ensure_ascii=False)[:200])
# 行业中性留存覆盖
row = d.get("factors") or d.get("per_factor") or {}
if isinstance(row, dict) and row:
    have = sum(1 for v in row.values()
               if isinstance(v, dict) and v.get("industry_neutral_retention") not in (None, ""))
    print("  留存覆盖: %d / %d" % (have, len(row)))
PYEOF
echo
echo "done $(date -Is)"
EOF
sed -i 's/\r$//' "$RUN/rehearsal/scale60.sh"
chmod +x "$RUN/rehearsal/scale60.sh"
setsid nohup bash "$RUN/rehearsal/scale60.sh" > "$OUT" 2>&1 < /dev/null &
echo "  已启动（detached，约 20 分钟）"
date -Is
