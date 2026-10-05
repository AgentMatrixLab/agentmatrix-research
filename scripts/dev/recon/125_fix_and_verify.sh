RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
PY=/home/data/conda-envs/rqsdk/bin/python
cd $REPO || exit 1
export PYTHONPATH=$REPO

echo "=== 部署前：服务器上的进包规则 ==="
sed -n '178,190p' research_core/factor_lab/delivery_manifest.py | sed 's/^/  /'
echo "  tier_sa 键存在: $(grep -c in_delivery_package_tier_sa research_core/factor_lab/delivery_manifest.py)"

echo
echo "=== 重跑 4b 交付清单 ==="
$PY -X utf8 -u scripts/build_delivery_manifest.py \
  --batch-manifest "$RUN/delivery/merged_oos/batch_manifest.json" \
  --candidates "$RUN/delivery/merged_oos/batch_candidates.csv" \
  --clusters-json "$RUN/delivery/strategy_demos/clusters.json" \
  --out "$RUN/delivery/delivery_manifest.csv" 2>&1 | tail -25

echo
echo "=== 重跑 9 交付说明 ==="
$PY -X utf8 -u scripts/build_delivery_readme.py --delivery-dir "$RUN/delivery" 2>&1 | tail -3

echo
echo "=== 校验：进包数是否 = validated 减去风险暴露 ==="
$PY -X utf8 - <<'PYEOF'
import csv, json, collections
rows = list(csv.DictReader(open("/home/data/agentmatrix_run/delivery/delivery_manifest.csv", encoding="utf-8-sig")))
summary = json.load(open("/home/data/agentmatrix_run/delivery/delivery_manifest.summary.json"))
validated = [r for r in rows if r["status"] == "validated"]
print("  validated           :", len(validated))
print("  其中风险暴露        :", sum(1 for r in validated if r["risk_exposure"] == "true"))
print("  其中 counts_as_alpha=false:", sum(1 for r in validated if r["counts_as_alpha"] == "false"))
inside = [r for r in rows if r["in_delivery_package"] == "true"]
print("  IN DELIVERY PACKAGE :", len(inside), "（修复前为 50）")
print("  summary 里的值      :", summary.get("in_delivery_package"))
print("  新增的 tier_sa 键   :", summary.get("in_delivery_package_tier_sa"))
expected = len(validated) - sum(1 for r in validated if r["risk_exposure"] == "true")
print("  一致性:", "OK" if len(inside) == expected else "** 不一致，期望 %d **" % expected)
print()
print("  tier 分布:", dict(collections.Counter(r["tier"] for r in rows)))
print("  说明：tier 现在只用于排序，不再是门槛")
PYEOF
date -Is
