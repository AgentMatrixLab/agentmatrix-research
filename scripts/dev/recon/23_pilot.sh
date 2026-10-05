cd /home/data/agentmatrix_run/agentmatrix
PY=/home/data/conda-envs/rqsdk/bin/python
RUN=/home/data/agentmatrix_run
export PYTHONPATH=$RUN/agentmatrix

echo "===== 构建 8 因子分层抽样清单 ====="
$PY -X utf8 - <<'EOF'
import csv, sys
sys.path.insert(0, "/home/data/agentmatrix_run/agentmatrix")
rows = list(csv.DictReader(open("/home/data/agentmatrix_run/candidate_list.csv", encoding="utf-8")))
by_family = {}
for r in rows:
    by_family.setdefault(r["factor_id"].split(":")[0], []).append(r)
sample = []
for fam in sorted(by_family):
    sample.append(by_family[fam][len(by_family[fam]) // 2])
    if len(sample) >= 8:
        break
with open(f"{'/home/data/agentmatrix_run'}/pilot_candidates.csv", "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0]))
    w.writeheader(); w.writerows(sample)
print(f"  {len(sample)} 因子: {[s['factor_id'] for s in sample]}")
EOF

echo
echo "===== 计量：build_factor_values ====="
/usr/bin/time -v $PY -X utf8 scripts/build_factor_values.py \
    --candidates $RUN/pilot_candidates.csv \
    --panel-file $RUN/panel/validation_panel.parquet \
    --config configs/validation_gates.yaml \
    --output $RUN/pilot/factor_values.parquet \
    --report $RUN/pilot/report.json 2>&1 | grep -E "candidates|panel:|rows |base factor|total series|Elapsed|Maximum resident|报告|report|s/factor|FAIL|failure" | head -20

echo
echo "===== 产物大小 ====="
ls -la $RUN/pilot/ 2>/dev/null
du -sh $RUN/pilot/factor_values.parquet 2>/dev/null

echo
echo "===== 计量：validate-batch (oos) ====="
/usr/bin/time -v $PY -X utf8 -m research_core.factor_lab.cli validate-batch \
    --candidates $RUN/pilot_candidates.csv \
    --config configs/validation_gates.yaml \
    --panel-file $RUN/panel/validation_panel.parquet \
    --factor-file $RUN/pilot/factor_values.parquet \
    --segment oos \
    --output-dir $RUN/pilot/batch 2>&1 | grep -E "validated|rejected|error|needs_human|Elapsed|Maximum resident" | head -15

echo
echo "===== 结果 ====="
$PY -X utf8 - <<'EOF'
import json, glob
for p in sorted(glob.glob("/home/data/agentmatrix_run/pilot/batch/../validation_runs/*/validation_result.json")):
    d = json.load(open(p))
    print(f"  {d['factor_id']:<20} status={d.get('status'):<12} failed={d.get('failed_gates')}")
m = json.load(open("/home/data/agentmatrix_run/pilot/batch/batch_manifest.json"))
print("  counts:", m.get("counts"))
EOF
