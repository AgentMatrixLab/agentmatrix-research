REH=/home/data/agentmatrix_run/rehearsal
PY=/home/data/conda-envs/rqsdk/bin/python

echo "=== 1. run_neworder.log 全文 ==="
cat "$REH/run_neworder.log" 2>/dev/null | head -60

echo
echo "=== 2. 产物时间戳（确认这次真的重写了）==="
ls -la "$REH/strategy_demos/" "$REH/delivery_manifest.csv" "$REH/delivery_manifest.summary.json" "$REH/live_signals/" 2>/dev/null

echo
echo "=== 3. clusters.json 内容摘要 ==="
$PY -X utf8 - <<'PYEOF'
import json, os
p = "/home/data/agentmatrix_run/rehearsal/strategy_demos/clusters.json"
if not os.path.exists(p):
    print("  clusters.json 不存在！")
else:
    d = json.load(open(p))
    print("  threshold      :", d.get("threshold"))
    print("  n_clusters     :", d.get("n_clusters"))
    print("  clustered      :", len(d.get("clustered_factors", [])))
    print("  representatives:", len(d.get("representatives", [])))
    reps = [r.get("representative") for r in d.get("representatives", [])]
    print("  rep ids        :", reps[:10])
    print("  source         :", str(d.get("source"))[:70])
PYEOF

echo
echo "=== 4. 交付清单摘要（聚类是否来自演示步骤）==="
cat "$REH/delivery_manifest.summary.json" 2>/dev/null
echo
$PY -X utf8 - <<'PYEOF'
import csv, collections
rows = list(csv.DictReader(open("/home/data/agentmatrix_run/rehearsal/delivery_manifest.csv", encoding="utf-8-sig")))
print("  行数:", len(rows))
print("  in_delivery_package=true:", sum(1 for r in rows if r["in_delivery_package"] == "true"))
print("  cluster_id 非空:", sum(1 for r in rows if r["cluster_id"]))
print("  cluster_role=representative:", sum(1 for r in rows if r["cluster_role"] == "representative"))
print("  fdr_accepted=true:", sum(1 for r in rows if r["fdr_accepted"] == "true"))
print("  industry_neutral_retention 非空:", sum(1 for r in rows if r["industry_neutral_retention"]))
PYEOF
date -Is
