RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
PY=/home/data/conda-envs/rqsdk/bin/python
cd $REPO || exit 1
export PYTHONPATH=$REPO

echo "=== 1. 链脚本语法（bash -n）==="
bash -n scripts/dev/run_downstream.sh && echo "  OK：run_downstream.sh 语法通过" || echo "  语法错误！"

echo
echo "=== 2. 关键阶段是否都在脚本里 ==="
for s in merge_batch_manifests consolidate_factor_values run_robustness_supplement \
         build_strategy_demos build_delivery_manifest build_live_signals; do
  n=$(grep -c "$s" scripts/dev/run_downstream.sh)
  printf "  %-30s 引用 %s 次\n" "$s" "$n"
done
echo "  --clusters-json 引用: $(grep -c 'clusters-json' scripts/dev/run_downstream.sh)"
echo "  --jobs 引用:          $(grep -c '\-\-jobs' scripts/dev/run_downstream.sh)"

echo
echo "=== 3. 新增/修改脚本可运行 ==="
$PY -X utf8 scripts/consolidate_factor_values.py --help >/dev/null 2>&1 && echo "  consolidate --help OK" || echo "  consolidate 失败"
$PY -X utf8 scripts/run_robustness_supplement.py --help >/dev/null 2>&1 && echo "  supplement  --help OK" || echo "  supplement 失败"
$PY -X utf8 scripts/build_live_signals.py --help >/dev/null 2>&1 && echo "  live_signals --help OK" || echo "  live_signals 失败"

echo
echo "=== 4. 交付文档已就位 ==="
ls -la docs/delivery/2026-10-07-execution-findings.md 2>/dev/null
echo "   行数: $(wc -l < docs/delivery/2026-10-07-execution-findings.md 2>/dev/null)"

echo
echo "=== 5. 冻结文件未被改动（与 pin 的 revision 对比）==="
echo "  COMMIT 文件: $(cat COMMIT)"
$PY -X utf8 - <<'PYEOF'
import hashlib
for f in ("configs/validation_gates.yaml",
          "research_core/factor_lab/deterministic_validation.py"):
    h = hashlib.sha256(open(f, "rb").read()).hexdigest()[:16]
    print("  %-58s sha256[:16]=%s" % (f, h))
src = open("research_core/factor_lab/deterministic_validation.py", encoding="utf-8").read()
for token in ("robustness", "streaming_supplement", "factor_value_stream", "consolidate"):
    print("  冻结验证器中 %-22s 出现次数: %d" % (token, src.count(token)))
PYEOF

echo
echo "=== 6. 守护进程 ==="
ps -eo pid,etime,args | awk '/retain_passing_values|mirror_runtime_data/ && !/awk/ {print "  " $1, $2, $4, $5}'

echo
echo "=== 7. pool ==="
echo "  oos 完成: $(ls $RUN/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l) / 213"
ps -eo pid,etime,args | awk '/run_one_shard\.sh [0-9]/ {print "  arg=" $NF, "etime=" $2}'
date -Is
