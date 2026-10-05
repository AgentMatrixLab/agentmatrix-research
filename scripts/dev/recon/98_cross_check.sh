RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
REH=$RUN/rehearsal
OUT=$REH/cross_check.log
cat > "$REH/cross_check.sh" <<'EOF'
#!/usr/bin/env bash
RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
PY=/home/data/conda-envs/rqsdk/bin/python
REH=$RUN/rehearsal
cd $REPO || exit 1
export PYTHONPATH=$REPO
echo "start $(date -Is)"
/usr/bin/time -f "CROSSCHECK wall=%es maxrss=%MkB" \
  $PY -X utf8 -u scripts/cross_check_delivery.py \
    --batch-manifest "$REH/merged_oos/batch_manifest.json" \
    --panel-file "$RUN/panel/validation_panel.parquet" \
    --candidates "$RUN/candidate_list.csv" \
    --config "$REPO/configs/validation_gates.yaml" \
    --output "$REH/cross_check.json" > "$REH/cross_check.stdout" 2>&1
echo "exit=$?"
echo "--- 摘要 ---"
$PY -X utf8 - <<'PYEOF'
import json, os
p = "/home/data/agentmatrix_run/rehearsal/cross_check.json"
if not os.path.exists(p):
    print("  没有生成 cross_check.json"); raise SystemExit(0)
d = json.load(open(p))
print("  finding_count:", d.get("finding_count"))
print("  checked      :", json.dumps(d.get("checked"), ensure_ascii=False)[:400])
for f in (d.get("findings") or [])[:25]:
    print("   ", json.dumps(f, ensure_ascii=False)[:240])
PYEOF
echo "done $(date -Is)"
EOF
sed -i 's/\r$//' "$REH/cross_check.sh"
chmod +x "$REH/cross_check.sh"
setsid nohup bash "$REH/cross_check.sh" > "$OUT" 2>&1 < /dev/null &
echo "  已启动 cross_check（detached）"
date -Is
