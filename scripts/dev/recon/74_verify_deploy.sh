REPO=/home/data/agentmatrix_run/agentmatrix
PY=/home/data/conda-envs/rqsdk/bin/python
cd $REPO || exit 1
export PYTHONPATH=$REPO

echo "=== 1. 新文件是否到位 ==="
for f in research_core/factor_lab/factor_value_stream.py \
         research_core/factor_lab/streaming_supplement.py \
         research_core/factor_lab/merge_batches.py \
         scripts/build_delivery_manifest.py \
         scripts/run_robustness_supplement.py; do
  if [ -f "$f" ]; then echo "  OK   $f  ($(wc -l < $f) 行)"; else echo "  缺失 $f"; fi
done

echo
echo "=== 2. 行尾检查（.py 无妨，但顺便看有无 CRLF）==="
for f in research_core/factor_lab/factor_value_stream.py research_core/factor_lab/streaming_supplement.py; do
  printf "  %s: CRLF=%s\n" "$f" "$(grep -c $'\r' "$f" 2>/dev/null || echo 0)"
done

echo
echo "=== 3. 导入自检 ==="
$PY -X utf8 - <<'PYEOF'
import sys
sys.path.insert(0, "/home/data/agentmatrix_run/agentmatrix")
from research_core.factor_lab.factor_value_stream import iter_factor_series, RowOrderReference
from research_core.factor_lab.streaming_supplement import (
    cross_sectional_correlation, neutral_retention_by_factor, prepare_panel,
)
from research_core.factor_lab.merge_batches import IDENTITY_FIELDS, merge_batch_manifests
print("  factor_value_stream   OK")
print("  streaming_supplement  OK")
print("  merge IDENTITY_FIELDS :", IDENTITY_FIELDS)
assert "factor_file_sha256" not in IDENTITY_FIELDS
print("  factor_file_sha256 已从跨分片恒等条件中移除 OK")
PYEOF

echo
echo "=== 4. 冻结验证器未被新增层 import（结构性保证）==="
grep -c "robustness" research_core/factor_lab/deterministic_validation.py || true
grep -c "streaming_supplement\|factor_value_stream" research_core/factor_lab/deterministic_validation.py || true
echo "  （两个计数都应为 0）"

echo
echo "=== 5. 用真实留存 parts 做一次小规模端到端（shard000+001 的 5 个通过因子）==="
PARTS=/home/data/agentmatrix_run/delivery/values/parts
ls -la $PARTS
$PY -X utf8 - <<'PYEOF'
import sys, glob, json, time
sys.path.insert(0, "/home/data/agentmatrix_run/agentmatrix")
from research_core.factor_lab.factor_value_stream import iter_factor_series, RowOrderReference
from research_core.factor_lab.streaming_supplement import cross_sectional_correlation

parts = sorted(glob.glob("/home/data/agentmatrix_run/delivery/values/parts/*.parquet"))
print("  parts:", len(parts))
t0 = time.time()
ids = []
ref = RowOrderReference()
for series in iter_factor_series(parts, reference=ref):
    ids.append(series.factor_id)
    print("    %-24s rows=%,d  dates=%s..%s" % (
        series.factor_id, len(series),
        str(series.dates[0].as_py())[:10], str(series.dates[-1].as_py())[:10]))
print("  读取 %d 个序列, %.1fs, 行序校验 %d 次" % (len(ids), time.time() - t0, ref.comparisons))
PYEOF
date -Is
