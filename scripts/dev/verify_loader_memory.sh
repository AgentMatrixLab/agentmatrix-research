#!/usr/bin/env bash
# Verify the loader memory fix BEFORE committing to a multi-hour run.
#
# Three runs have now died to OOM, twice because I tuned shard size instead of
# finding what memory actually scaled with. This measures the fix directly: load
# one real factor file and report peak RSS. Budget one minute, not one hour.
#
# Usage:  verify_loader_memory.sh [shard_dir]
set -u

RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
PY=/home/data/conda-envs/rqsdk/bin/python
SHARD=${1:-}

cd "$REPO" || exit 1
export PYTHONPATH="$REPO"

echo "=== 环境 ==="
free -g | head -2
df -h / | tail -1

if [ -z "$SHARD" ]; then
  SHARD=$(ls -d "$RUN"/shards/shard* 2>/dev/null | head -1)
fi
if [ -z "$SHARD" ] || [ ! -f "$SHARD/factor_values.parquet" ]; then
  echo "没有可用的因子文件，先生成一个小样本："
  "$PY" -X utf8 - "$RUN" <<'PYEOF'
import csv, os, sys
run = sys.argv[1]
rows = list(csv.DictReader(open(run + "/candidate_list.csv", encoding="utf-8")))
sample = rows[:4]
target = run + "/memtest"
os.makedirs(target, exist_ok=True)
with open(target + "/candidate_list.csv", "w", encoding="utf-8", newline="") as fh:
    writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(sample)
print("  写入", target + "/candidate_list.csv", len(sample), "个因子")
PYEOF
  SHARD=$RUN/memtest
  /usr/bin/time -f "build wall=%es maxrss=%MkB" \
    "$PY" -X utf8 -u scripts/build_factor_values.py \
      --candidates "$SHARD/candidate_list.csv" \
      --panel-file "$RUN/panel/validation_panel.parquet" \
      --config configs/validation_gates.yaml \
      --output "$SHARD/factor_values.parquet" \
      --emit-start 2020-01-02 2>&1 | tail -6
fi

echo
echo "=== 因子文件规模 ==="
ls -la "$SHARD/factor_values.parquet"
"$PY" -X utf8 - "$SHARD/factor_values.parquet" <<'PYEOF'
import sys, pyarrow.parquet as pq
f = pq.ParquetFile(sys.argv[1])
print(f"  rows={f.metadata.num_rows:,}  row_groups={f.metadata.num_row_groups}")
PYEOF

echo
echo "=== 关键测量：加载该文件需要多少内存 ==="
/usr/bin/time -v "$PY" -X utf8 - "$SHARD/factor_values.parquet" <<'PYEOF' 2>&1 | grep -E "rows loaded|series|Elapsed \(wall|Maximum resident"
import sys
from research_core.factor_lab.precomputed_factors import load_precomputed_factors
pre = load_precomputed_factors(sys.argv[1])
print(f"  rows loaded: {sum(len(s) for s in pre.series.values()):,}")
print(f"  series     : {len(pre.series)}")
PYEOF

echo
echo "对照：修复前，一个 158 序列 / 14.9 亿行的分片加载后峰值 48.5 GB 并被 OOM 杀掉。"
echo "若此处峰值低于 10 GB，说明修复生效，可以放心提高并行度。"
