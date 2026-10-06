RUN=/home/data/agentmatrix_run
OUT=$RUN/rehearsal/scale50.log
cat > "$RUN/rehearsal/scale50.sh" <<'EOF'
#!/usr/bin/env bash
RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
PY=/home/data/conda-envs/rqsdk/bin/python
W=$RUN/rehearsal/scale50
rm -rf "$W"; mkdir -p "$W"
cd $REPO || exit 1
export PYTHONPATH=$REPO
echo "start $(date -Is)  shards=$(ls $RUN/shards/shard*/oos/batch_manifest.json | wc -l)"

echo
echo "########## 批次范围 + 合并 ##########"
$PY -X utf8 -u scripts/build_batch_candidates.py \
  --run "$RUN" --candidates "$RUN/candidate_list.csv" \
  --output "$W/batch_candidates.csv" | tail -3
$PY -X utf8 -u scripts/merge_batch_manifests.py \
  --shards $RUN/shards/shard*/oos/batch_manifest.json \
  --candidates "$W/batch_candidates.csv" \
  --output-dir "$W/merged" | $PY -X utf8 -c "
import json, sys
d = json.load(sys.stdin)
c = d['counts']
print('  shards=%s candidates=%s validated=%s rejected=%s' % (
    d['shard_count'], d['candidate_count'], c['validated'], c['rejected']))
print('  code_commit lengths present:', sorted({len(x) for x in (
    d.get('identity', {}).get('code_commit') or [''] if isinstance(d.get('identity', {}).get('code_commit'), list)
    else [d.get('identity', {}).get('code_commit') or '']) }))
"

echo
echo "########## 交叉验证（独立重算每个哈希）##########"
/usr/bin/time -f "CROSSCHECK wall=%es maxrss=%MkB" \
  $PY -X utf8 -u scripts/cross_check_delivery.py \
    --batch-manifest "$W/merged/batch_manifest.json" \
    --panel-file "$RUN/panel/validation_panel.parquet" \
    --candidates "$W/batch_candidates.csv" \
    --config "$REPO/configs/validation_gates.yaml" \
    --output "$W/cross_check.json" > "$W/cross_check.stdout" 2>&1
echo "  exit=$?"
$PY -X utf8 -u - "$W/cross_check.json" <<'PYEOF'
import json, sys
d = json.load(open(sys.argv[1]))
print("  finding_count:", d.get("finding_count"))
for f in (d.get("findings") or [])[:6]:
    print("   ", json.dumps(f, ensure_ascii=False)[:200])
# 核对哈希覆盖：每个因子结果都应被重算
checked = d.get("checked") or {}
print("  重算项:", {k: v for k, v in checked.items() if k in
      ("result_hash", "manifest_artifact", "report_artifact", "result_artifact", "panel", "config")})
PYEOF
echo "done $(date -Is)"
EOF
sed -i 's/\r$//' "$RUN/rehearsal/scale50.sh"
chmod +x "$RUN/rehearsal/scale50.sh"
setsid nohup bash "$RUN/rehearsal/scale50.sh" > "$OUT" 2>&1 < /dev/null &
echo "  已启动（detached，低内存，约 4 分钟）"
date -Is
