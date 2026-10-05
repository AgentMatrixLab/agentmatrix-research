RUN=/home/data/agentmatrix_run
PY=/home/data/conda-envs/rqsdk/bin/python
echo "=== 交付清单摘要 ==="
cat "$RUN/delivery/delivery_manifest.summary.json"
echo
echo "=== 25 列清单里各状态的计数，以及为什么没进包 ==="
$PY -X utf8 - <<'PYEOF'
import csv, collections
rows = list(csv.DictReader(open("/home/data/agentmatrix_run/delivery/delivery_manifest.csv", encoding="utf-8-sig")))
print("  行数:", len(rows))
print("  status:", dict(collections.Counter(r["status"] for r in rows)))
print("  counts_as_alpha:", dict(collections.Counter(r["counts_as_alpha"] for r in rows)))
print("  risk_exposure:", dict(collections.Counter(r["risk_exposure"] for r in rows)))
validated = [r for r in rows if r["status"] == "validated"]
print()
print("  validated 共 %d 个，其中:" % len(validated))
print("    counts_as_alpha=false :", sum(1 for r in validated if r["counts_as_alpha"] == "false"))
print("    risk_exposure=true    :", sum(1 for r in validated if r["risk_exposure"] == "true"))
print("    进包                  :", sum(1 for r in validated if r["in_delivery_package"] == "true"))
print()
print("  被判为风险暴露（不进包）的因子:")
for r in validated:
    if r["in_delivery_package"] != "true":
        print("    %-28s counts_as_alpha=%-6s risk_exposure=%s" % (
            r["factor_id"], r["counts_as_alpha"], r["risk_exposure"]))
PYEOF
echo
echo "=== 候选清单里 risk_exposure 的真实分布（决定 300 需要多少片）==="
$PY -X utf8 - <<'PYEOF'
import csv, collections
rows = list(csv.DictReader(open("/home/data/agentmatrix_run/candidate_list.csv", encoding="utf-8")))
print("  授权候选总数:", len(rows))
c = collections.Counter((r.get("risk_exposure") or "").strip().lower() for r in rows)
print("  risk_exposure 取值分布:", dict(c))
alpha = sum(1 for r in rows if (r.get("risk_exposure") or "").strip().lower() not in ("true", "1", "yes"))
expo = len(rows) - alpha
print("  非暴露（可计入 alpha）: %d （%.1f%%）" % (alpha, 100.0 * alpha / len(rows)))
print("  风险暴露             : %d （%.1f%%）" % (expo, 100.0 * expo / len(rows)))
print()
passed, total = 74, 132
rate = passed / total
print("  实测过闸率 %.1f%%" % (100 * rate))
print("  每片 4 个候选 → 每片通过 %.2f 个，其中可计入 alpha 约 %.2f 个" % (
    4 * rate, 4 * rate * alpha / len(rows)))
need = 300 / (4 * rate * alpha / len(rows))
print("  交付 300 个需约 %.0f 片（此前按未计入暴露率估计为 134 片）" % need)
PYEOF
date -Is
