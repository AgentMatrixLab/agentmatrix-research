RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
PY=/home/data/conda-envs/rqsdk/bin/python
W=$RUN/rehearsal/trigger_check
OUT=$RUN/rehearsal/trigger_check.log
cat > "$RUN/rehearsal/trigger_check.sh" <<'EOF'
#!/usr/bin/env bash
RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
PY=/home/data/conda-envs/rqsdk/bin/python
W=$RUN/rehearsal/trigger_check
rm -rf "$W"; mkdir -p "$W"
cd $REPO || exit 1
export PYTHONPATH=$REPO
echo "start $(date -Is)"

echo
echo "########## 1. auto_deliver 的 passing() 计数 ##########"
$PY -X utf8 - "$RUN" <<'PYEOF'
import glob, json, sys
run = sys.argv[1]
total = 0
for path in glob.glob(f"{run}/shards/shard*/oos/batch_manifest.json"):
    payload = json.load(open(path))
    for result in payload.get("results", []):
        if result.get("status") == "validated" and not result.get("failed_gates"):
            total += 1
print("  passing() =", total)
PYEOF

echo
echo "########## 2. 链条自己的计数（build_batch_candidates + merge）##########"
$PY -X utf8 -u scripts/build_batch_candidates.py \
  --run "$RUN" --candidates "$RUN/candidate_list.csv" \
  --output "$W/batch_candidates.csv" | tail -3
$PY -X utf8 -u scripts/merge_batch_manifests.py \
  --shards $RUN/shards/shard*/oos/batch_manifest.json \
  --candidates "$W/batch_candidates.csv" \
  --output-dir "$W/merged" | $PY -X utf8 -c "
import json, sys
d = json.load(sys.stdin)
print('  merge validated =', d['counts']['validated'])
print('  merge rejected  =', d['counts']['rejected'])
print('  shard_count     =', d['shard_count'])
print('  candidate_count =', d['candidate_count'])
"

echo
echo "########## 3. 一致性判定 ##########"
$PY -X utf8 - "$RUN" "$W/merged/batch_manifest.json" <<'PYEOF'
import glob, json, sys
run, merged_path = sys.argv[1], sys.argv[2]
passing = 0
for path in glob.glob(f"{run}/shards/shard*/oos/batch_manifest.json"):
    payload = json.load(open(path))
    for result in payload.get("results", []):
        if result.get("status") == "validated" and not result.get("failed_gates"):
            passing += 1
merged = json.load(open(merged_path))
validated = merged["counts"]["validated"]
print(f"  passing()={passing}  merge.validated={validated}  "
      f"{'一致 -> 触发阈值可信' if passing == validated else '** 不一致，阈值需要重定 **'}")

# 风险暴露会从交付包里剔除，量化它对 300 的影响
risk = 0
import csv
for row in csv.DictReader(open(f"{run}/candidate_list.csv", encoding="utf-8")):
    if str(row.get("risk_exposure", "")).strip().lower() in ("true", "1", "yes"):
        risk += 1
print(f"  候选中的风险暴露: {risk} / {merged['candidate_count']} 相关候选")
print(f"  ⇒ 阈值 308 时预计进包约 {308 - risk} 个（承诺 300）")
PYEOF
echo "done $(date -Is)"
EOF
sed -i 's/\r$//' "$RUN/rehearsal/trigger_check.sh"
chmod +x "$RUN/rehearsal/trigger_check.sh"
setsid nohup bash "$RUN/rehearsal/trigger_check.sh" > "$OUT" 2>&1 < /dev/null &
echo "  已启动（detached，低内存）"
date -Is
