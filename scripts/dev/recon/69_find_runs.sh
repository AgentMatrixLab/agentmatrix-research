RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
echo "=== 1. runs 目录实际内容 ==="
ls -d $REPO/data/factor_lab/validation_runs/*/ 2>/dev/null | wc -l
ls $REPO/data/factor_lab/validation_runs/ 2>/dev/null | head -40
echo
echo "=== 2. 全盘搜索 validation_result.json（限制层级）==="
find $RUN -maxdepth 6 -name 'validation_result.json' 2>/dev/null | sed 's|^|  |' | head -60
echo "  总数: $(find $RUN -maxdepth 6 -name 'validation_result.json' 2>/dev/null | wc -l)"
echo
echo "=== 3. 全盘搜索 validation_runs 目录 ==="
find $RUN -maxdepth 6 -type d -name 'validation_runs' 2>/dev/null | sed 's|^|  |'
echo
echo "=== 4. run-1 的 10 个分片里，声称通过门槛的因子 ==="
/home/data/conda-envs/rqsdk/bin/python -X utf8 - <<'PYEOF'
import glob, json, collections
rows = []
for p in sorted(glob.glob("/home/data/agentmatrix_run/reference/run1/manifests/shard*/oos.json")):
    rows.extend(json.load(open(p)).get("results", []))
passed = sorted(r["factor_id"] for r in rows
                if r.get("status") == "validated" and not r.get("failed_gates"))
print("  通过门槛:", len(passed))
for f in passed:
    print("   ", f)
print()
validated = sorted(r["factor_id"] for r in rows if r.get("status") == "validated")
print("  status=validated 总数:", len(validated))
print("  总结果数:", len(rows))
# 每个结果的 artifact 路径
print()
print("  抽样 artifact 路径:")
for r in rows[:6]:
    print("   ", r["factor_id"], "->", (r.get("artifacts") or {}).get("result"))
PYEOF
echo
echo "=== 5. 报告目录内容（前 20）==="
ls $REPO/data/factor_lab/ 2>/dev/null | head -20
date -Is
