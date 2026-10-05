RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
PY=/home/data/conda-envs/rqsdk/bin/python
RUNS=$RUN/runtime_mirror/data/factor_lab/validation_runs
OUT=$RUN/delivery
cd $REPO || exit 1
export PYTHONPATH=$REPO

echo "=== 按链中的确切参数重跑 4b ==="
$PY -X utf8 -u scripts/build_delivery_manifest.py \
    --candidates "$RUN/candidate_list.csv" \
    --batch-manifest "$OUT/merged_oos/batch_manifest.json" \
    --runs-dir "$RUNS" \
    --supplementary "$OUT/supplementary_report.json" \
    --clusters-json "$OUT/strategy_demos/clusters.json" \
    --out "$OUT/delivery_manifest.csv" 2>&1 | tail -22

echo
echo "=== 重跑 9 ==="
$PY -X utf8 -u scripts/build_delivery_readme.py --delivery-dir "$OUT" 2>&1 | tail -2

echo
echo "=== 校验（这次应 849 行、进包 74、tier/FDR 有值）==="
$PY -X utf8 - <<'PYEOF'
import csv, json, collections
rows = list(csv.DictReader(open("/home/data/agentmatrix_run/delivery/delivery_manifest.csv", encoding="utf-8-sig")))
s = json.load(open("/home/data/agentmatrix_run/delivery/delivery_manifest.summary.json"))
print("  行数            :", len(rows))
print("  status          :", dict(collections.Counter(r["status"] for r in rows)))
print("  tier            :", dict(collections.Counter(r["tier"] for r in rows)))
print("  fdr_accepted    :", dict(collections.Counter(r["fdr_accepted"] for r in rows)))
inside = [r for r in rows if r["in_delivery_package"] == "true"]
print("  IN DELIVERY     :", len(inside))
print("  summary         : validated=%s in_delivery_package=%s tier_sa=%s fdr_accepted=%s clusters=%s" % (
    s.get("validated"), s.get("in_delivery_package"), s.get("in_delivery_package_tier_sa"),
    s.get("fdr_accepted"), s.get("delivered_clusters")))
ok = (len(rows) == 849 and len(inside) == s.get("in_delivery_package") == 74)
print("  一致性          :", "OK" if ok else "** 需检查 **")
print()
print("  进包因子都是 validated 且非暴露:",
      all(r["status"] == "validated" and r["risk_exposure"] != "true" for r in inside))
PYEOF
date -Is
