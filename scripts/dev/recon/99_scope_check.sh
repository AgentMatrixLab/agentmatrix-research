RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
OUT=$RUN/rehearsal/scope_check.log
cat > "$RUN/rehearsal/scope_check.sh" <<'EOF'
#!/usr/bin/env bash
RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
PY=/home/data/conda-envs/rqsdk/bin/python
WORK=$RUN/rehearsal/scope
rm -rf "$WORK"; mkdir -p "$WORK"
cd $REPO || exit 1
export PYTHONPATH=$REPO
echo "start $(date -Is)"

echo "--- 1. 生成批次候选清单（已完成分片的并集）---"
$PY -X utf8 -u scripts/build_batch_candidates.py \
  --run "$RUN" --candidates "$RUN/candidate_list.csv" \
  --output "$WORK/batch_candidates.csv"

echo
echo "--- 2. 用批次清单合并分片 manifest ---"
$PY -X utf8 -u scripts/merge_batch_manifests.py \
  --shards $RUN/shards/shard*/oos/batch_manifest.json \
  --candidates "$WORK/batch_candidates.csv" \
  --output-dir "$WORK/merged"

echo
echo "--- 3. 交叉验证（这一步以前会报 candidate_count 不一致）---"
$PY -X utf8 -u scripts/cross_check_delivery.py \
  --batch-manifest "$WORK/merged/batch_manifest.json" \
  --panel-file "$RUN/panel/validation_panel.parquet" \
  --candidates "$WORK/batch_candidates.csv" \
  --config "$REPO/configs/validation_gates.yaml" \
  --output "$WORK/cross_check.json"
echo "cross_check exit=$?"
$PY -X utf8 - <<'PYEOF'
import json
d = json.load(open("/home/data/agentmatrix_run/rehearsal/scope/cross_check.json"))
print("  finding_count:", d.get("finding_count"))
for f in (d.get("findings") or [])[:10]:
    print("   ", json.dumps(f, ensure_ascii=False)[:220])
PYEOF
echo "done $(date -Is)"
EOF
sed -i 's/\r$//' "$RUN/rehearsal/scope_check.sh"
chmod +x "$RUN/rehearsal/scope_check.sh"
setsid nohup bash "$RUN/rehearsal/scope_check.sh" > "$OUT" 2>&1 < /dev/null &
echo "  已启动（detached）"
date -Is
