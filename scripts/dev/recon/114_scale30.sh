RUN=/home/data/agentmatrix_run
OUT=$RUN/rehearsal/scale30.log
cat > "$RUN/rehearsal/scale30.sh" <<'EOF'
#!/usr/bin/env bash
RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
PY=/home/data/conda-envs/rqsdk/bin/python
W=$RUN/rehearsal/scale30
rm -rf "$W"; mkdir -p "$W"
cd $REPO || exit 1
export PYTHONPATH=$REPO
echo "start $(date -Is)"

echo
echo "########## 1. 批次候选范围（已完成分片的并集）##########"
$PY -X utf8 -u scripts/build_batch_candidates.py \
  --run "$RUN" --candidates "$RUN/candidate_list.csv" \
  --output "$W/batch_candidates.csv"

echo
echo "########## 2. 合并分片 manifest ##########"
$PY -X utf8 -u scripts/merge_batch_manifests.py \
  --shards $RUN/shards/shard*/oos/batch_manifest.json \
  --candidates "$W/batch_candidates.csv" \
  --output-dir "$W/merged" | $PY -X utf8 -c "
import json,sys
d=json.load(sys.stdin)
print('  shard_count   :', d['shard_count'])
print('  candidate_count:', d['candidate_count'])
print('  counts        :', d['counts'])
print('  code_commit   :', d.get('identity',{}).get('code_commit'))
"

echo
echo "########## 3. 合并因子值 parts（30 个分片，约 5.8 亿行）##########"
/usr/bin/time -f "CONSOLIDATE wall=%es maxrss=%MkB" \
  $PY -X utf8 -u scripts/consolidate_factor_values.py \
    --parts "$RUN/delivery/values/parts" \
    --output "$W/factor_values.parquet"
echo "  exit=$?"
$PY -X utf8 -u - "$W/factor_values.parquet" <<'PYEOF'
import json, sys
from pathlib import Path
p = Path(sys.argv[1])
side = json.loads(Path(str(p) + ".json").read_text())
per = sorted({v["rows"] for v in side["factors"].values()})
n = len(side["factors"])
print("  rows=%s  factors=%d  rows/series=%s" % (format(side["row_count"], ","), n,
      format(per[0], ",") if per else "-"))
print("  算术校验 %d x %s = %s  == row_count %s" % (
    n, format(per[0], ",") if per else "-", format(n * per[0], ",") if per else "-",
    "YES" if per and n * per[0] == side["row_count"] else "NO"))
PYEOF

echo
echo "########## 4. 交叉验证（30 分片规模）##########"
/usr/bin/time -f "CROSSCHECK wall=%es maxrss=%MkB" \
  $PY -X utf8 -u scripts/cross_check_delivery.py \
    --batch-manifest "$W/merged/batch_manifest.json" \
    --panel-file "$RUN/panel/validation_panel.parquet" \
    --candidates "$W/batch_candidates.csv" \
    --config "$REPO/configs/validation_gates.yaml" \
    --output "$W/cross_check.json" > "$W/cross_check.stdout" 2>&1
echo "  cross_check exit=$?（0 = 无发现）"
$PY -X utf8 -u - "$W/cross_check.json" <<'PYEOF'
import json, sys
d = json.load(open(sys.argv[1]))
print("  finding_count:", d.get("finding_count"))
for f in (d.get("findings") or [])[:8]:
    print("   ", json.dumps(f, ensure_ascii=False)[:200])
print("  已核对:", json.dumps(d.get("checked"), ensure_ascii=False)[:260])
PYEOF
echo "done $(date -Is)"
EOF
sed -i 's/\r$//' "$RUN/rehearsal/scale30.sh"
chmod +x "$RUN/rehearsal/scale30.sh"
setsid nohup bash "$RUN/rehearsal/scale30.sh" > "$OUT" 2>&1 < /dev/null &
echo "  已启动（detached，低内存）"
date -Is
