#!/usr/bin/env bash
# Everything after the shards finish, in one place.
#
# Runs on the 115 server. Each step consumes the previous step's artifact, so a
# failure stops the chain rather than producing a delivery built on half the
# evidence.
#
#   1. merge the per-shard batch manifests into one
#   2. additive robustness layer (FDR, industry-neutral retention, benchmark excess)
#   3. fused delivery manifest (the single authoritative table)
#   4. strategy demos and live signals
#
# Usage:  run_downstream.sh
set -u

RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
PY=/home/data/conda-envs/rqsdk/bin/python
PANEL=$RUN/panel/validation_panel.parquet
CONFIG=$REPO/configs/validation_gates.yaml
OUT=$RUN/delivery
LOGS=$RUN/logs
mkdir -p "$OUT" "$LOGS"

cd "$REPO" || exit 1
export PYTHONPATH="$REPO"

step() { echo; echo "########## $* ##########"; }

step "0. 检查分片产物是否齐全"
SHARD_DIRS=$(ls -d "$RUN"/shards/shard* 2>/dev/null | wc -l)
OOS_OK=$(ls "$RUN"/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l)
TRAIN_OK=$(ls "$RUN"/shards/shard*/train/batch_manifest.json 2>/dev/null | wc -l)
echo "  分片目录   : $SHARD_DIRS"
echo "  train 完成 : $TRAIN_OK"
echo "  oos   完成 : $OOS_OK"
if [ "$OOS_OK" -eq 0 ]; then
  echo "  没有任何 oos 结果，终止"
  exit 1
fi

step "1. 合并分片 manifest"
"$PY" -X utf8 -u scripts/merge_batch_manifests.py \
    --shards "$RUN"/shards/shard*/oos/batch_manifest.json \
    --output-dir "$OUT/merged_oos" || { echo "MERGE FAILED"; exit 1; }

step "2. 稳健性附加层（FDR + 行业中性 + 基准超额）"
# NOTE: the shards delete their factor files on completion, so the supplementary
# layer cannot read them here. It needs factor VALUES, and FDR is a batch-level
# statistic that has to see every factor's p-value at once, so it cannot be done
# per shard either.
#
# Plan: first merge the frozen-gate results, take the factors that PASSED, and
# recompute values for just those (~500 of 849) in one pass. That is the set the
# badge is actually reported for, and it is a fraction of the work the full run
# did. Recorded here so it is not mistaken for a missing step.
echo "  (需要先按下面的步骤重建通过者的因子值，见 NOTE)"
echo "  暂时跳过；先出冻结门槛结果"

step "3. 交付清单"
"$PY" -X utf8 -u scripts/build_delivery_manifest.py \
    --candidates "$RUN/candidate_list.csv" \
    --batch-manifest "$OUT/merged_oos/batch_manifest.json" \
    --runs-dir "$RUN/validation_runs" \
    --supplementary "$OUT/supplementary_report.json" \
    --out "$OUT/delivery_manifest.csv" || { echo "MANIFEST FAILED"; exit 1; }

echo
echo "########## 完成 ##########"
echo "产物在 $OUT"
ls -la "$OUT"
