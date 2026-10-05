RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
echo "=== 1. 每个分片记录的 code_commit（决定合并可行性）==="
/home/data/conda-envs/rqsdk/bin/python -X utf8 - <<'PYEOF'
import glob, json, os
for p in sorted(glob.glob("/home/data/agentmatrix_run/shards/shard*/oos/batch_manifest.json")):
    pl = json.load(open(p))
    tag = p.split("/")[-3]
    print("  %s  commit=%s   written=%s" % (
        tag, pl.get("code_commit"), pl.get("created_at_utc")))
PYEOF
echo
echo "=== 2. 服务器仓库状态 ==="
cd $REPO || exit 1
echo "  HEAD      : $(git rev-parse HEAD 2>&1)"
echo "  branch    : $(git rev-parse --abbrev-ref HEAD 2>&1)"
echo "  工作区脏? : $(git status --porcelain 2>&1 | head -20)"
echo "  COMMIT 文件: $(cat $REPO/COMMIT 2>/dev/null || echo '(不存在)')"
echo "  AGENTMATRIX_COMMIT env: ${AGENTMATRIX_COMMIT:-（未设置）}"
echo "  git log -3:"
git log --oneline -3 2>&1 | sed 's/^/    /'
echo
echo "  .git 存在? $([ -d $REPO/.git ] && echo yes || echo no)"
echo
echo "=== 3. 下游脚本是否齐备 ==="
for s in scripts/merge_batch_manifests.py scripts/rebuild_passing_factors.py \
         scripts/run_robustness_supplement.py scripts/build_delivery_manifest.py \
         scripts/build_strategy_demos.py scripts/build_factor_values.py \
         scripts/dev/run_downstream.sh research_core/strategy_operations/signal_pipeline.py; do
  if [ -f "$REPO/$s" ]; then echo "  OK   $s"; else echo "  缺失 $s"; fi
done
echo
echo "=== 4. 通过的 21 个因子里，risk_exposure 标记情况（关系到能否计入交付）==="
/home/data/conda-envs/rqsdk/bin/python -X utf8 - <<'PYEOF'
import glob, json, collections
rows = []
for p in sorted(glob.glob("/home/data/agentmatrix_run/shards/shard*/oos/batch_manifest.json")):
    rows.extend(json.load(open(p)).get("results", []))
passed = [r for r in rows if r.get("status") == "validated" and not r.get("failed_gates")]
print("  validated(无失败门槛): %d" % len(passed))
re_ = [r for r in passed if r.get("risk_exposure")]
print("  其中 risk_exposure=True: %d" % len(re_))
print("  有效 alpha (无风险暴露): %d" % (len(passed) - len(re_)))
allv = [r for r in rows if r.get("status") == "validated"]
print("  status=validated 总数: %d" % len(allv))
print()
print("  一个通过样本的全部字段:")
print(json.dumps(passed[0], ensure_ascii=False, indent=4)[:2000])
PYEOF
echo
echo "=== 5. 当前在跑的分片 ==="
ps -eo pid,etime,rss,args | awk '/run_one_shard/ && !/awk/ {print "  " $0}'
date -Is
