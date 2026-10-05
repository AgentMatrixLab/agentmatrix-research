REPO=/home/data/agentmatrix_run/agentmatrix
cd $REPO || exit 1
export PYTHONPATH=$REPO
/home/data/conda-envs/rqsdk/bin/python -X utf8 - <<'PYEOF'
import json, statistics
from pathlib import Path

REPO = Path("/home/data/agentmatrix_run/agentmatrix")
runs_dir = REPO / "data" / "factor_lab" / "validation_runs"
paths = sorted(runs_dir.glob("*/validation_result.json"))
print("validation_result.json 数量:", len(paths))

results = []
for p in paths:
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        print("  跳过", p.parent.name, type(exc).__name__)
        continue
    payload.setdefault("factor_id", p.parent.name)
    results.append(payload)

validated = [r for r in results if r.get("status") == "validated" and not r.get("failed_gates")]
print("其中 status=validated 且无失败门槛:", len(validated))

from research_core.factor_lab.scoring import score_batch

batch = score_batch(results)
print()
print("=== score_batch ===")
print("  n_scored :", batch["n_scored"])
print("  n_skipped:", batch["n_skipped"])
print("  tiers    :", batch["tier_counts"])

# 只看通过冻结门槛的
passed_ids = {r["factor_id"] for r in validated}
scored_passed = [f for f in batch["factors"] if f["factor_id"] in passed_ids]
print()
print("=== 通过八道冻结门槛的因子，其评分卡表现 ===")
print("  数量:", len(scored_passed))
comps = [f["composite"] for f in scored_passed if f["composite"] == f["composite"]]
if comps:
    comps_sorted = sorted(comps)
    print("  composite: min=%.1f p25=%.1f 中位=%.1f p75=%.1f max=%.1f" % (
        comps_sorted[0],
        comps_sorted[len(comps_sorted)//4],
        statistics.median(comps_sorted),
        comps_sorted[3*len(comps_sorted)//4],
        comps_sorted[-1]))
    for thr in (75.0, 55.0, 50.0, 45.0, 40.0):
        n = sum(1 for c in comps if c >= thr)
        print("    composite >= %5.1f : %3d / %d = %.0f%%" % (thr, n, len(comps), 100.0*n/len(comps)))
    print()
    print("  最差 5 个:")
    for f in sorted(scored_passed, key=lambda x: (x["composite"] if x["composite"]==x["composite"] else -1))[:5]:
        print("    %-28s composite=%6.2f tier=%s missing=%s" % (
            f["factor_id"], f["composite"], f["tier"], ",".join(f["missing_dimensions"])))
    print("  最好 5 个:")
    for f in sorted(scored_passed, key=lambda x: -(x["composite"] if x["composite"]==x["composite"] else -1))[:5]:
        print("    %-28s composite=%6.2f tier=%s missing=%s" % (
            f["factor_id"], f["composite"], f["tier"], ",".join(f["missing_dimensions"])))

print()
print("=== 一个样本的各维度原始值（看什么在拖分）===")
if scored_passed:
    if scored_passed:
        f = scored_passed[0]
        print("  factor:", f["factor_id"], " composite=%.2f tier=%s" % (f["composite"], f["tier"]))
        print("  weight_available=%s coverage=%.2f" % (f["weight_available"], f["weight_coverage"]))
        for d in f["dimensions"]:
            print("    %-18s w=%4.1f raw=%-14s score=%6.3f points=%5.2f" % (
                d["name"], d["weight"], d["raw"], d["score"], d["points"]))
        print("  missing:", f["missing_dimensions"])
print()
print("=== 全部有 composite 的因子的 tier 分布（含未过门槛的）===")
allc = [(f["factor_id"], f["composite"], f["tier"]) for f in batch["factors"]]
import collections
print("  ", collections.Counter(t for _, _, t in allc))
PYEOF
