#!/usr/bin/env bash
# Sharded full validation run on the 115 server.
#
# Why sharded: on the real 9,444,457-row panel a single candidate costs roughly
# 75 seconds end to end (base expression plus both perturbation variants), so 849
# candidates is about 17.7 hours single-threaded. Memory is the binding constraint
# on parallelism rather than cores -- one worker holds ~15 GB -- so the wave size
# is chosen from measured RSS, not from `nproc`.
#
# Each shard is independent and self-cleaning: it builds its own factor values,
# runs train and oos validation, keeps only the (small) results, and deletes the
# (multi-GB) factor file. Peak disk is therefore one shard's factor values rather
# than the whole run's, which matters because all 849 candidates would need
# roughly 130 GB and only ~139 GB is free.
#
# Usage:  run_sharded.sh <shards> <parallel>
set -u

RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
PY=/home/data/conda-envs/rqsdk/bin/python
PANEL=$RUN/panel/validation_panel.parquet
CONFIG=$REPO/configs/validation_gates.yaml
SHARDS=${1:-16}
PARALLEL=${2:-4}
LOGS=$RUN/logs
mkdir -p "$LOGS" "$RUN/shards"

cd "$REPO" || exit 1
export PYTHONPATH="$REPO"

echo "=== 切分 $SHARDS 片 ==="
$PY -X utf8 - "$SHARDS" <<'EOF'
import csv, sys, os
shards = int(sys.argv[1])
run = "/home/data/agentmatrix_run"
rows = list(csv.DictReader(open(f"{run}/candidate_list.csv", encoding="utf-8")))
# Interleave by family so each shard sees a mix, rather than one shard being all
# ALPHA360 and another all NONE. Round-robin over the catalog order is enough and
# keeps shards balanced in size.
buckets = [[] for _ in range(shards)]
for index, row in enumerate(rows):
    buckets[index % shards].append(row)
for index, bucket in enumerate(buckets):
    target = f"{run}/shards/shard{index:02d}"
    os.makedirs(target, exist_ok=True)
    with open(f"{target}/candidate_list.csv", "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(bucket)
    families = sorted({r["factor_id"].split(":")[0] for r in bucket})
    print(f"  shard{index:02d}: {len(bucket)} 因子  家族={','.join(families)}")
EOF

run_shard() {
  local i=$1
  local dir=$RUN/shards/shard$(printf "%02d" "$i")
  local log=$LOGS/shard$(printf "%02d" "$i").log"
  {
    echo "### shard $i 开始 $(date -Is)"
    echo "--- 1. 计算因子值 ---"
    /usr/bin/time -f "build wall=%es maxrss=%MkB" \
      $PY -X utf8 scripts/build_factor_values.py \
        --candidates "$dir/candidate_list.csv" \
        --panel-file "$PANEL" \
        --config "$CONFIG" \
        --output "$dir/factor_values.parquet" \
        --report "$dir/build_report.json" || { echo "BUILD FAILED"; exit 1; }

    echo "--- 2. 训练段验证 ---"
    /usr/bin/time -f "train wall=%es maxrss=%MkB" \
      $PY -X utf8 -m research_core.factor_lab.cli validate-batch \
        --candidates "$dir/candidate_list.csv" \
        --config "$CONFIG" \
        --panel-file "$PANEL" \
        --factor-file "$dir/factor_values.parquet" \
        --segment train \
        --output-dir "$dir/train" || { echo "TRAIN FAILED"; exit 1; }

    echo "--- 3. 样本外验证 ---"
    /usr/bin/time -f "oos wall=%es maxrss=%MkB" \
      $PY -X utf8 -m research_core.factor_lab.cli validate-batch \
        --candidates "$dir/candidate_list.csv" \
        --config "$CONFIG" \
        --panel-file "$PANEL" \
        --factor-file "$dir/factor_values.parquet" \
        --segment oos \
        --output-dir "$dir/oos" || { echo "OOS FAILED"; exit 1; }

    echo "--- 4. 释放因子文件 ---"
    du -sh "$dir/factor_values.parquet" 2>/dev/null
    rm -f "$dir/factor_values.parquet"
    echo "### shard $i 完成 $(date -Is)"
  } > "$log" 2>&1
}

echo
echo "=== 开跑：$SHARDS 片，并发 $PARALLEL ==="
START=$(date +%s)
RUNNING=0
for i in $(seq 0 $((SHARDS-1))); do
  run_shard "$i" &
  RUNNING=$((RUNNING+1))
  if [ "$RUNNING" -ge "$PARALLEL" ]; then
    wait -n 2>/dev/null || wait
    RUNNING=$((RUNNING-1))
  fi
  # 每波给一次磁盘与内存快照
  echo "  [$(date +%H:%M:%S)] 已启动 $((i+1))/$SHARDS  内存可用=$(free -g | awk '/Mem:/{print $7}')GB  磁盘可用=$(df -h / | awk 'NR==2{print $4}')"
done
wait
END=$(date +%s)
echo
echo "=== 全部完成，用时 $(( (END-START)/60 )) 分钟 ==="
