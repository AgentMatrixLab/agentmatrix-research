RUN=/home/data/agentmatrix_run
REH=$RUN/rehearsal
PY=/home/data/conda-envs/rqsdk/bin/python

echo "=== 交付清单摘要（最关键：in_delivery_package）==="
cat "$REH/delivery_manifest.summary.json"
echo
echo "=== 补充层摘要 ==="
$PY -X utf8 - <<'PYEOF'
import json
r = json.load(open("/home/data/agentmatrix_run/rehearsal/supplementary_report.json"))
print("  summary:", json.dumps(r["summary"], ensure_ascii=False))
print("  marginal:", json.dumps(r["marginal_effect"], ensure_ascii=False)[:300])
n = 0
for f in r["factors"]:
    if f.get("industry_neutral_ic"):
        n += 1
print("  有行业中性留存的因子:", n, "/", len(r["factors"]))
for f in r["factors"][:5]:
    ic = f.get("industry_neutral_ic")
    print("    %-26s p=%.4g fdr=%s retention=%s" % (
        f["factor_id"], f["p_value"], f["fdr_accepted"],
        "None" if not ic else round(ic["retention"], 4)))
PYEOF

echo
echo "=== 策略演示产物 ==="
ls -la "$REH/strategy_demos/" 2>/dev/null
$PY -X utf8 - <<'PYEOF'
import json, os
p = "/home/data/agentmatrix_run/rehearsal/strategy_demos/strategies.json"
if os.path.exists(p):
    d = json.load(open(p))
    print("  data_status:", d.get("data_status"))
    for s in d.get("strategies", []):
        print("    %-34s n_factors=%s traded=%s" % (
            s["strategy_id"], s["n_factors"], s.get("mean_traded_fraction")))
b = "/home/data/agentmatrix_run/rehearsal/strategy_demos/backtest_results.json"
if os.path.exists(b):
    d = json.load(open(b))
    print("  backtest_window:", d.get("backtest_window"))
    for k, v in d.get("results", {}).items():
        m = v.get("metrics", {})
        print("    %-34s metrics=%s" % (k, json.dumps(m, ensure_ascii=False)[:200]))
else:
    print("  backtest_results.json 不存在")
PYEOF

echo
echo "=== 实盘信号 ==="
ls -la "$REH/live_signals/" 2>/dev/null || echo "  live_signals 目录不存在（步骤 5b 未产出）"

echo
echo "=== 交付清单：25 列 + 在包数量 ==="
head -1 "$REH/delivery_manifest.csv" | tr ',' '\n' | nl | tr '\n' ' '
echo
$PY -X utf8 - <<'PYEOF'
import csv, collections
rows = list(csv.DictReader(open("/home/data/agentmatrix_run/rehearsal/delivery_manifest.csv", encoding="utf-8-sig")))
print("  总行数:", len(rows))
print("  status:", dict(collections.Counter(r["status"] for r in rows)))
print("  in_delivery_package=true:", sum(1 for r in rows if r["in_delivery_package"] == "true"))
print("  tier:", dict(collections.Counter(r["tier"] for r in rows)))
print("  fdr_accepted=true:", sum(1 for r in rows if r["fdr_accepted"] == "true"))
print("  cluster_id 非空:", sum(1 for r in rows if r["cluster_id"]))
print()
for r in rows[:3]:
    print("   ", {k: r[k] for k in ("factor_id","status","tier","composite","fdr_accepted",
                                    "industry_neutral_retention","cluster_id","cluster_role",
                                    "in_delivery_package")})
PYEOF
date -Is
